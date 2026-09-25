# Lab VM templates: build the small one first

Every VM lab is a **full clone** of a golden template on the hypervisor
(`orchestration/proxmox.py` → `provision`). The template you pick is therefore
paid for on every single launch: once in disk copied, and then continuously in
RAM and vCPU for as long as a student holds the instance.

Use case A runs the whole platform on **one Proxmox workstation**
([usecase-a-baremetal.md](usecase-a-baremetal.md)), so that bill is the
difference between a class of thirty launching together and a class of thirty
queueing. This document is the recipe for the small template the shipped labs
use, and the rule for when a lab has earned a bigger one.

---

## The rule

> **A lab gets the smallest template that can run its tasks, and Kali only
> when the lab actually uses offensive tooling.**

Reach for `kali-web` when the lab's tasks *are* `nmap`, `sqlmap`, `burpsuite`,
`hashcat`, Metasploit. Everything else — reading logs, writing files, grepping,
answering questions on a box — is `debian12-min`.

`log-triage` ("Log Triage Under Fire") is the worked example of getting this
wrong. It was seeded against `Kali-Template`, and its entire student-facing
task is:

```sh
mkdir -p /root/answers
echo '...' > /root/answers/source-ip.txt
```

The incident it is about lives in the **lesson text**, not on the box
(`academy_content/soc-analyst/02-reading-auth-logs-at-speed.md`), and the
grader reads those four files back over the QEMU guest agent. `grep`, a shell,
and the agent is the complete requirement. A Kali clone for that is roughly
twenty times the disk and four times the RAM of what the work needs, and it
buys the student nothing. It now ships against `debian12-min` at 1 vCPU / 1 GB.

## Sizing is now binding, not advisory

A Proxmox clone inherits the golden image's `cores` and `memory`, so before
this a lab published as "1 vCPU / 1 GB" could boot as 4 vCPU / 8 GB while
tenant quota (`api/instances.py`) cheerfully charged it as 1 and 1.

`provision` now pushes the template's declared `cpu` and `ram_gb` onto the
clone in the same config call that attaches the tenant VLAN. Two consequences:

* **Declare the size you mean.** It is what the VM gets, and what quota
  charges. The two can no longer drift apart.
* **The golden image's memory no longer matters**, but its **disk** still
  does — that is fixed at build time and every clone copies it. Keep the
  template's disk small; that is the number you cannot override later.

## Reserved VMID ranges

| Range | Owner |
|---|---|
| `900` | malware-sandbox Windows template (`SBX_TEMPLATE_VMID`) |
| `9000–9099` | malware-sandbox clones (`SBX_CLONE_VMID_MIN/MAX`) |
| `8000–8099` | **golden lab templates** (this document) |
| everything else | lab clones, allocated by `/cluster/nextid` |

Keep lab templates out of the sandbox's ranges; the coordinator recycles
`9000–9099` without asking who is using them.

## Build `debian12-min` (VMID 8001)

The Debian generic cloud image is already minimal and already brings up DHCP,
so there is no ISO install to sit through. It does **not** ship
`qemu-guest-agent` — verified by booting one: the VM runs, cloud-init runs, and
`qm agent <vmid> ping` stays silent. Since the agent is what publishes the
lab's address and what the grader reads answers through, install it into the
image before the template is built. On the Proxmox host:

```sh
cd /var/lib/vz/template/iso
wget https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2

qm create 8001 --name debian12-min --ostype l26 \
  --memory 1024 --cores 1 --agent enabled=1 \
  --net0 virtio,bridge=vmbr1 \
  --scsihw virtio-scsi-single --serial0 socket --vga serial0
qm importdisk 8001 debian-12-genericcloud-amd64.qcow2 local-lvm
qm set 8001 --scsi0 local-lvm:vm-8001-disk-0 --boot order=scsi0
qm set 8001 --ide2 local-lvm:cloudinit
qm disk resize 8001 scsi0 4G
```

Now prepare the guest. `virt-customize` (from `libguestfs-tools`, already
present on a Proxmox node) edits the disk offline, so there is no first boot to
log into and no throwaway credential to clean up afterwards. Three things have
to be true in the image, and the `debian-12-genericcloud` base gets none of
them right on its own:

- **`ssh.service` must be enabled.** The genericcloud image ships `sshd` but
  leaves the service *disabled*, so a clone boots, gets a lease, and answers
  ARP while nothing ever listens on port 22 — the exact failure that reads as
  "the lab is unreachable" when the guest is fine.
- **`PasswordAuthentication` must be `yes`.** The image sets it to `no`, so
  even with `sshd` running a student's password is refused.
- **`qemu-guest-agent` must be enabled.** `provision` waits on the agent for
  the VM's address, and the checker reads answer files through it.

`systemctl enable` inside the libguestfs appliance does not reliably create the
`multi-user.target.wants` symlinks, so create them directly. The banner every
lab shows on login (`/etc/motd`) goes in here too:

```sh
qm stop 8001 2>/dev/null   # only if it was started
# openssh-server and qemu-guest-agent are already in the genericcloud image;
# --install only runs apt if they are missing (needs host internet then).
virt-customize -a /dev/pve/vm-8001-disk-0 \
  --install openssh-server,qemu-guest-agent \
  --upload /root/palestrix-motd:/etc/motd \
  --write /etc/ssh/sshd_config.d/60-palestrix.conf:'PasswordAuthentication yes' \
  --run-command 'sed -i "s/^PasswordAuthentication no/PasswordAuthentication yes/" /etc/ssh/sshd_config' \
  --link /lib/systemd/system/ssh.service:/etc/systemd/system/multi-user.target.wants/ssh.service \
  --link /lib/systemd/system/qemu-guest-agent.service:/etc/systemd/system/multi-user.target.wants/qemu-guest-agent.service \
  --run-command 'chmod 644 /etc/motd /etc/ssh/sshd_config.d/60-palestrix.conf'
```

**Bake fixed SSH host keys too.** Labs are ephemeral and the tenant VLAN reuses
a small pool of addresses, so a student who connects to `10.24.0.178` today and
to a *different* lab on `10.24.0.178` next week would get SSH's "REMOTE HOST
IDENTIFICATION HAS CHANGED" alarm every time — each clone otherwise generates
its own host keys on first boot. Generate one set of keys, upload them, and
tell cloud-init to stop regenerating them (`ssh_deletekeys: false`), so every
lab presents the same key and the warning never fires:

```sh
mkdir -p /root/labhostkeys && cd /root/labhostkeys
ssh-keygen -t ed25519 -N '' -f ssh_host_ed25519_key -q
ssh-keygen -t rsa -b 3072 -N '' -f ssh_host_rsa_key -q
ssh-keygen -t ecdsa -N '' -f ssh_host_ecdsa_key -q
printf 'ssh_deletekeys: false\n' > /root/99-palestrix-hostkeys.cfg
virt-customize -a /dev/pve/vm-8001-disk-0 \
  --upload /root/labhostkeys/ssh_host_ed25519_key:/etc/ssh/ssh_host_ed25519_key \
  --upload /root/labhostkeys/ssh_host_ed25519_key.pub:/etc/ssh/ssh_host_ed25519_key.pub \
  --upload /root/labhostkeys/ssh_host_rsa_key:/etc/ssh/ssh_host_rsa_key \
  --upload /root/labhostkeys/ssh_host_rsa_key.pub:/etc/ssh/ssh_host_rsa_key.pub \
  --upload /root/labhostkeys/ssh_host_ecdsa_key:/etc/ssh/ssh_host_ecdsa_key \
  --upload /root/labhostkeys/ssh_host_ecdsa_key.pub:/etc/ssh/ssh_host_ecdsa_key.pub \
  --upload /root/99-palestrix-hostkeys.cfg:/etc/cloud/cloud.cfg.d/99-palestrix-hostkeys.cfg \
  --run-command 'chmod 600 /etc/ssh/ssh_host_*_key'
```

Sharing one host key across every ephemeral lab is a deliberate trade: these
VMs are behind the overlay and already share one login, so host authentication
buys nothing, and the alternative is an alarm students learn to click through —
the worst security posture of all.

The alternative to any of this — boot it, SSH in, `apt install` — needs a
cloud-init login and a network the lab VLAN deliberately does not have, so
prefer the offline edit.

Four gigabytes of disk is deliberate: it is the number every clone copies.

Give it a **known** student login through cloud-init. Set a real password, not
`openssl passwd` with no argument (that reads an empty password and bakes a
hash nobody can reproduce). The value is the one the connect modal shows every
student — `PALESTRIX_LAB_SSH_PASSWORD` on the API must match it:

```sh
qm set 8001 --ciuser student --cipassword 'PalestrixLab2026' --ipconfig0 ip=dhcp
```

> **The guest agent is not optional.** Automated checking reads answer files
> through `agent/file-read`, and `provision` waits on the agent for the VM's
> address before it will publish an SSH target. A template without a running
> `qemu-guest-agent` produces a lab that never comes up and a grader that
> scores every submission zero. Verify with `qm agent 8001 ping` **before**
> converting.

Boot it once, confirm the agent answers and `sshd` is up, then shut down and
convert:

```sh
qm template 8001
```

`debian12-min` is now the name teachers type into the lab publish form, and
the name `labs_catalog.py` ships.

## Build `kali-web` (VMID 8002), only if a lab needs it

Same shape, from the Kali installer ISO, with the headless metapackage rather
than the default desktop — a VM lab with `access_mode=no-gui` is reached over
SSH and never renders that desktop for anyone:

```sh
apt install -y kali-linux-headless qemu-guest-agent
systemctl enable --now qemu-guest-agent
```

Then `qm template 8002`. Size labs that use it at 2 vCPU / 2 GB and expect the
clone to cost real disk; that is the trade you are making on purpose.

## Repointing a lab that was already seeded

`ensure_labs` is **insert-only** on purpose (`labs_catalog.py`): a template
whose slug already exists is skipped, so a teacher's edits are never
overwritten by a restart. That also means an instance seeded before this
change still holds `Kali-Template` in its database, and re-running the catalog
will not fix it. There is no PATCH endpoint for lab templates, so repoint it
directly, once, against the platform database:

```sql
UPDATE lab_templates
   SET vm_template = 'debian12-min', cpu = 1, ram_gb = 1
 WHERE slug = 'log-triage';
```

The four capstone labs (`soc-capstone`, `web-capstone`, `netdef-capstone`,
`forensics-capstone`) shipped already pointing at `debian12-min`, so they need
no repointing -- only that the template exists before anyone launches one.

Running instances keep the VM they were cloned from; the next launch gets the
small one. Check first with:

```sql
SELECT slug, kind, vm_template, cpu, ram_gb FROM lab_templates;
```

## Checking what an instance actually got

```sh
qm config <clone-vmid> | grep -E 'cores|memory|net0'
```

and in the platform, the instance log line `vm: sized to 1 vCPU, 1 GB RAM`
records what `provision` asked for.
