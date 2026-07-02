/*
 * MOCK DATA for the Phase 1 templates. Every value in this file is sample
 * data and is replaced by live API responses from Phase 2 onward
 * (see docs/public-api.md for the real contracts).
 *
 * Names are invented, locale-appropriate handles and people. No real
 * students, grades, or infrastructure are represented.
 */

export type InstanceState = "provisioning" | "running" | "stopped" | "expired";

export const currentUser = {
  name: "Rafaela Almazan",
  handle: "rafalmz",
  role: "Student" as const,
  palestras: 1385,
  streakDays: 11,
  communityScore: 742,
};

export const activeInstance = {
  id: "lab-3427",
  name: "Blue Team: Log Triage Under Fire",
  course: "Defensive Operations 201",
  state: "running" as InstanceState,
  kind: "container" as const,
  access: { mode: "no-gui" as const, host: "10.24.7.31", port: 2211, proto: "ssh" },
  node: "pve-01",
  tenant: "hau-bscs-3a",
  ttlTotalMin: 90,
  ttlRemainingSec: 2537,
  startedAt: "2026-07-02T09:14:22+08:00",
};

export const provisioningSample = [
  { t: "09:14:02", level: "info" as const, msg: "queue: job accepted (tenant hau-bscs-3a, quota 2/3 instances)" },
  { t: "09:14:03", level: "info" as const, msg: "docker: pulling registry.palestrix.local/labs/log-triage:1.4" },
  { t: "09:14:09", level: "info" as const, msg: "docker: layer 7f3a2c11 extracted (34.2 MB)" },
  { t: "09:14:12", level: "info" as const, msg: "network: attached to isolated bridge net-hau-bscs-3a" },
  { t: "09:14:14", level: "info" as const, msg: "firewall: tenant egress policy applied (deny-all, allow 10.24.7.0/24)" },
  { t: "09:14:18", level: "info" as const, msg: "container: started, healthcheck 1/3" },
  { t: "09:14:21", level: "ok" as const, msg: "healthcheck passed, ssh exposed on 10.24.7.31:2211" },
  { t: "09:14:22", level: "ok" as const, msg: "instance running, TTL reaper armed for 90 min" },
];

export const paths = [
  { slug: "soc-analyst", title: "SOC Analyst", modules: 14, done: 9, hours: 31, certified: false },
  { slug: "web-exploitation", title: "Web Exploitation", modules: 12, done: 12, hours: 26, certified: true },
  { slug: "network-defense", title: "Network Defense", modules: 10, done: 3, hours: 22, certified: false },
  { slug: "digital-forensics", title: "Digital Forensics", modules: 11, done: 0, hours: 25, certified: false },
];

export const modules = [
  { title: "Reading auth logs at speed", path: "SOC Analyst", state: "done" as const, palestras: 40 },
  { title: "Sigma rules from scratch", path: "SOC Analyst", state: "done" as const, palestras: 55 },
  { title: "Lateral movement patterns", path: "SOC Analyst", state: "current" as const, palestras: 60 },
  { title: "Building a triage runbook", path: "SOC Analyst", state: "locked" as const, palestras: 45 },
  { title: "Capstone: 48-hour incident", path: "SOC Analyst", state: "locked" as const, palestras: 120 },
];

export const courses = [
  { code: "CS 3712", title: "Defensive Operations 201", students: 38, assignments: 6, section: "BSCS 3A" },
  { code: "CS 3719", title: "Offensive Security Fundamentals", students: 41, assignments: 8, section: "BSCS 3B" },
  { code: "IT 4204", title: "Digital Forensics Practicum", students: 27, assignments: 4, section: "BSIT 4A" },
];

export const assignments = [
  { title: "Lab: Log Triage Under Fire", type: "Ephemeral lab", due: "2026-07-08", submitted: 21, total: 38, state: "open" },
  { title: "Quiz: TCP fundamentals", type: "Quiz", due: "2026-07-04", submitted: 36, total: 38, state: "open" },
  { title: "Writeup: pico-forensics 3", type: "Writeup", due: "2026-06-27", submitted: 38, total: 38, state: "graded" },
];

export const leaderboard = [
  { rank: 1, handle: "0xkidlat", score: 4310, delta: "+120", firstBloods: 7 },
  { rank: 2, handle: "amihan", score: 4185, delta: "+85", firstBloods: 5 },
  { rank: 3, handle: "gab_lockpick", score: 3970, delta: "+40", firstBloods: 4 },
  { rank: 4, handle: "rafalmz", score: 3742, delta: "+210", firstBloods: 2 },
  { rank: 5, handle: "duwende", score: 3618, delta: "+0", firstBloods: 3 },
];

export const challenges = [
  { id: "web-04", title: "Cookie Monster's Bakery", category: "Web", points: 250, solves: 18, firstBlood: "0xkidlat", solved: true },
  { id: "web-05", title: "GraphQL Overshare", category: "Web", points: 350, solves: 7, firstBlood: "amihan", solved: false },
  { id: "cry-03", title: "Repeating Pad", category: "Crypto", points: 200, solves: 24, firstBlood: "gab_lockpick", solved: true },
  { id: "for-02", title: "Deleted But Not Gone", category: "Forensics", points: 300, solves: 11, firstBlood: "0xkidlat", solved: false },
  { id: "pwn-01", title: "Stack Overflow Literal", category: "Pwn", points: 400, solves: 4, firstBlood: "duwende", solved: false },
  { id: "osi-02", title: "Geoguesser: Pampanga", category: "OSINT", points: 150, solves: 31, firstBlood: "amihan", solved: true },
];

export const firstBloodFeed = [
  { handle: "amihan", challenge: "GraphQL Overshare", ago: "4m" },
  { handle: "0xkidlat", challenge: "Deleted But Not Gone", ago: "38m" },
  { handle: "duwende", challenge: "Stack Overflow Literal", ago: "2h" },
];

export const writeups = [
  { title: "Repeating Pad: XOR is not a vault", author: "amihan", tags: ["crypto", "xor"], votes: 47, comments: 12, ago: "3h" },
  { title: "How I found the GraphQL introspection leak", author: "0xkidlat", tags: ["web", "graphql"], votes: 34, comments: 8, ago: "1d" },
  { title: "Log triage: a 15-minute runbook", author: "rafalmz", tags: ["blue-team", "siem"], votes: 29, comments: 15, ago: "2d" },
  { title: "Volatility 3 cheatsheet for the forensics path", author: "duwende", tags: ["forensics", "memory"], votes: 22, comments: 4, ago: "4d" },
];

export const sandboxAnalyses = [
  { id: "det-0917", file: "invoice_scan.pdf.exe", sha256: "9f86d081884c7d65", verdict: "malicious", submitted: "11:02", fsEvents: 214, netEvents: 12 },
  { id: "det-0916", file: "grade-macro.xlsm", sha256: "60303ae22b998861", verdict: "suspicious", submitted: "10:41", fsEvents: 58, netEvents: 3 },
  { id: "det-0915", file: "putty-0.81-installer.exe", sha256: "fd61a03af4f77d87", verdict: "clean", submitted: "09:58", fsEvents: 131, netEvents: 0 },
];

export const fsEvents = [
  { time: "11:02:14.221", pid: 4312, op: "CreateFile", path: "C:\\Users\\lab\\AppData\\Roaming\\svhost.exe", flag: "malicious" },
  { time: "11:02:14.309", pid: 4312, op: "SetRegistry", path: "HKCU\\...\\Run\\WindowsUpdater", flag: "malicious" },
  { time: "11:02:15.114", pid: 4312, op: "WriteFile", path: "C:\\Users\\lab\\Documents\\readme_decrypt.txt", flag: "suspicious" },
  { time: "11:02:15.827", pid: 4318, op: "DeleteFile", path: "C:\\Windows\\Temp\\st4g3r.tmp", flag: "suspicious" },
  { time: "11:02:16.023", pid: 4318, op: "ReadFile", path: "C:\\Users\\lab\\Desktop\\notes.docx", flag: "info" },
];

export const netEvents = [
  { time: "11:02:17.441", proto: "TCP", dest: "185.220.101.34", port: 443, bytes: "14.2 KB", flag: "malicious" },
  { time: "11:02:18.902", proto: "DNS", dest: "cdn-metrics-sync.top", port: 53, bytes: "0.3 KB", flag: "malicious" },
  { time: "11:02:21.166", proto: "TCP", dest: "10.99.0.2", port: 445, bytes: "2.1 KB", flag: "suspicious" },
];

export const nodes = [
  { name: "pve-01", role: "Proxmox VE 8.3", cpu: 62.4, memUsedGb: 187.2, memTotalGb: 256, vms: 34, state: "online" },
  { name: "pve-02", role: "Proxmox VE 8.3", cpu: 41.8, memUsedGb: 121.7, memTotalGb: 256, vms: 27, state: "online" },
  { name: "sandbox-01", role: "Isolated Docker host", cpu: 12.3, memUsedGb: 18.4, memTotalGb: 64, vms: 3, state: "online" },
];

export const tenants = [
  { name: "hau-bscs-3a", instances: 14, quota: 24, cpuCap: "48 vCPU", ramCap: "96 GB", network: "10.24.7.0/24" },
  { name: "hau-bscs-3b", instances: 19, quota: 24, cpuCap: "48 vCPU", ramCap: "96 GB", network: "10.24.8.0/24" },
  { name: "clctf-open", instances: 41, quota: 64, cpuCap: "128 vCPU", ramCap: "256 GB", network: "10.31.0.0/22" },
];

export const isoLibrary = [
  { name: "kali-linux-2026.2-installer-amd64.iso", size: "4.1 GB", uploaded: "2026-06-18", by: "sir.delacruz" },
  { name: "ubuntu-24.04.2-live-server-amd64.iso", size: "2.6 GB", uploaded: "2026-06-11", by: "sir.delacruz" },
  { name: "winserver-2022-eval.iso", size: "5.3 GB", uploaded: "2026-05-30", by: "admin.ops" },
];

export const instanceRegistry = [
  { id: "lab-3427", owner: "rafalmz", template: "log-triage:1.4", kind: "CT", node: "pve-01", state: "running" as InstanceState, ttl: "00:42:17" },
  { id: "lab-3426", owner: "duwende", template: "kali-web:2.1", kind: "VM", node: "pve-02", state: "running" as InstanceState, ttl: "01:12:03" },
  { id: "lab-3425", owner: "amihan", template: "forensics-win11:3.0", kind: "VM", node: "pve-01", state: "provisioning" as InstanceState, ttl: "02:00:00" },
  { id: "lab-3421", owner: "gab_lockpick", template: "pwn-arena:1.9", kind: "CT", node: "pve-02", state: "stopped" as InstanceState, ttl: "00:00:00" },
  { id: "lab-3390", owner: "bea.santi", template: "kali-web:2.1", kind: "VM", node: "pve-01", state: "expired" as InstanceState, ttl: "00:00:00" },
];

export const stateLabel: Record<InstanceState, string> = {
  provisioning: "Provisioning",
  running: "Running",
  stopped: "Stopped",
  expired: "Expired",
};
