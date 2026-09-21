---
summary: Where the intrusion usually starts, and where user intent is recorded in more detail than anywhere else on the system.
---

# Browser and application artifacts

Most intrusions begin in a browser, and most insider cases are proved in one.
The browser records where someone went, what they downloaded, what they typed
into a search box and roughly when — at a level of detail no other application
matches.

## The files, by browser

Chromium-family browsers (Chrome, Edge, Brave, Opera) keep SQLite databases
under the profile directory:

```
History          urls, visits, downloads, keyword_search_terms
Cookies          including session cookies, values encrypted
Login Data       saved credentials, encrypted
Web Data         autofill, saved addresses and cards
Top Sites        most-visited
Sessions/        open tabs at last run -- what was on screen
Cache/           cached responses, often the actual downloaded content
```

Firefox uses `places.sqlite` (history and bookmarks), `cookies.sqlite`,
`formhistory.sqlite`, and `sessionstore-backups/`.

They are ordinary SQLite files, so query them directly:

```sql
SELECT datetime(v.visit_time/1000000 - 11644473600, 'unixepoch') AS visited,
       u.url, u.title, v.transition
FROM   visits v JOIN urls u ON u.id = v.url_id
ORDER  BY v.visit_time;
```

## Epochs: get this right or every time is wrong

Different applications count from different moments, and mixing them produces
timestamps that are decades off:

- **Chromium (WebKit):** microseconds since 1601-01-01. Subtract
  11644473600 after converting to seconds.
- **Firefox (PRTime):** microseconds since 1970-01-01.
- **Unix:** seconds since 1970-01-01.
- **Windows FILETIME:** 100-nanosecond intervals since 1601-01-01.

If a converted timestamp lands in 1601 or 2367, you used the wrong epoch.

## Transition types: how they got there

Chromium records *how* each visit happened, and this is the field that
separates intent from accident:

- `link` — followed a link.
- `typed` — typed the address. Deliberate.
- `auto_bookmark`, `reload`, `form_submit`.
- `redirect` chains — arrived without choosing to.

A `typed` visit to a data-exfiltration site is a different fact from a
redirect chain that ended there. In an insider case that distinction is
frequently the case.

## Downloads

The `downloads` table gives the source URL, the target path on disk, the
referring page, byte counts and start and end times. This is often the first
line of a timeline: the file arrived here, from there, at this moment, because
the user was on that page.

Cross-reference with the **`Zone.Identifier`** alternate data stream on the
downloaded file, which independently records that it came from the internet
and frequently the host it came from.

## Private browsing, and why it is not

Incognito does not write history to disk, but it leaks:

- **Memory.** URLs, page content and form data sit in RAM for the life of the
  process — another reason to capture memory.
- **DNS.** The resolver logged every lookup regardless.
- **The page file and hibernation file**, where that memory may have landed.
- **Downloads.** The file itself is still written to disk, with its
  `Zone.Identifier`.
- **Cache artefacts and crash dumps** that sometimes persist anyway.

"They used incognito" narrows the evidence; it does not remove it.

## Beyond the browser

- **Email clients.** `.pst` and `.ost` for Outlook, `maildir` or `.mbox`
  elsewhere. Headers carry routing and timing.
- **Chat.** Slack, Teams, Discord and Signal Desktop all keep local SQLite or
  LevelDB stores. Signal encrypts its database with a key stored locally,
  which means it is recoverable from an imaged profile.
- **Cloud sync clients.** Dropbox, OneDrive and Google Drive keep local
  databases listing every synced file — including files that were removed from
  the local disk but remain in the cloud. This is one of the highest-yield
  artefacts in an exfiltration case.
- **Office.** Recent-files lists, autosave copies, and document metadata with
  author and revision history.
- **`LNK` files and Jump Lists.** Created when a file is opened, and they
  persist after the target is deleted — proving a file existed, its path, and
  its size.

## Check yourself

- Why does the Chromium `transition` field matter more than the URL in an
  insider investigation?
- Name three places evidence of private browsing survives.
- Why is a cloud sync client's local database often more valuable than the
  files on disk?
