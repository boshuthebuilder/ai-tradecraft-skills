---
name: private-repo-access
description: >-
  Get a person with no GitHub account read access to a private GitHub repository, so they can use the
  plugin or tool it holds: make an SSH key on their own computer, write the message they send to the
  repository's owner (who adds it as a read-only deploy key), then test the key, clone the repository and
  hand over to that repository's own setup guide. Written for a person with no coding background, run once
  in Claude Code (the Code tab of the Claude desktop app), not in Cowork, whose sandbox has no SSH. Use when
  someone says "I don't have a GitHub account" for a private repository or an upstream plugin such as one
  listed under this marketplace's "Upstream plugins", or asks "how do I get access without GitHub",
  "set up a deploy key", "I can't install this plugin, the repo is private".
---

# Private repository access without a GitHub account

A private repository normally needs a GitHub account with access to it. A person who has no account, and
does not want one, can still read one repository through a **deploy key**: an SSH key that the
repository's owner adds to that repository, read-only. It gives that one computer read access to that one
repository, and nothing else. The owner can remove it at any time.

This skill does the whole job for a person with no coding background. Claude runs every command, explains
each one in a plain sentence first, and asks before anything that installs software or needs a password.
The person does three things: approve the commands, send one message to the owner, and say when the owner
has replied.

## Where it runs

- **Run it in Claude Code on the person's own computer.** The Code tab of the Claude desktop app is Claude
  Code. The key must live on that computer, because later updates (`git pull`) and the repository's own
  setup run there.
- **Not in Cowork.** Cowork runs commands in an isolated Linux sandbox. In the sandbox, SSH to GitHub does
  not connect (observed 2026-11-01), and a key made there would not reach the person's computer. After the
  setup, the person goes back to Cowork for everyday use, if the repository's guide says so.
- **The steps are written for macOS.** On Linux the commands are the same except the clipboard command
  (step 6). Windows is not covered.

## Words used here

- **The person**: who wants access and has no GitHub account.
- **The owner**: an admin of the private repository. A collaborator with write access cannot add deploy
  keys; only an admin can.
- **The repository**: `<owner>/<name>` on GitHub. `<name>` below is the part after the slash.

## Safety rules

- [ ] Never show, print, copy or send the **private** key (the file without `.pub`). Only the `.pub` file
      leaves the computer.
- [ ] Never overwrite an existing key file or an existing `Host github.com` entry. If either exists, stop
      and explain (see *When something is different*).
- [ ] Ask the owner for **read-only** access. The message says to leave "Allow write access" unticked.
- [ ] Ask before installing anything, and before any command that asks for the computer's password.
- [ ] One key per repository per computer. GitHub refuses a key that is already a deploy key elsewhere.

## Part 1 — make the key and the message

1. **Find the repository.** If the person names it, use it. If they name a plugin listed under *Upstream
   plugins* in this marketplace's `README.md`, take the repository from that entry (the marketplace's local copy is under
   `~/.claude/plugins/marketplaces/`). Confirm `<owner>/<name>`
   with the person before going on.
2. **Check for git.** Run `git --version`. On a Mac without it, macOS offers to install Apple's command line
   developer tools: tell the person to click **Install** in that dialog, and wait until it finishes.
3. **Make the key, unless it already exists.** The key file is `~/.ssh/<name>_deploy`.

   ```bash
   mkdir -p ~/.ssh && chmod 700 ~/.ssh
   test -e ~/.ssh/<name>_deploy || ssh-keygen -t ed25519 -f ~/.ssh/<name>_deploy -N "" -C "<name> deploy key"
   ```

   The key has no passphrase, so nothing prompts for one later. Say so to the person: anyone who can use
   their computer account can read the repository.
4. **Point SSH at the key.** Check `~/.ssh/config` for a `Host github.com` line first. If there is none,
   append:

   ```text
   Host github.com
     IdentityFile ~/.ssh/<name>_deploy
     IdentitiesOnly yes
   ```

   Claude Code's plugin installer connects to `git@github.com` itself, so the entry must be for
   `github.com`, not for an alias.
5. **Record GitHub's host key.** Run `ssh -o StrictHostKeyChecking=accept-new -T git@github.com`. The
   answer is `Permission denied (publickey)`, because the owner has not added the key yet. That is
   expected. The command's purpose is to store GitHub's host key in `~/.ssh/known_hosts`: Claude Code's own
   SSH check refuses unknown hosts, and without the stored key it would fall back to HTTPS, which cannot
   read a private repository without an account.
6. **Copy the public key.** `pbcopy < ~/.ssh/<name>_deploy.pub` on macOS (`xclip -selection clipboard`
   or `wl-copy` on Linux). Also show the one line in the chat. It starts with `ssh-ed25519`.
7. **Write the message to the owner.** Fill in the template below and show it in the chat, ready to paste
   into an email or a text. The person sends it; Claude does not.
8. **Stop.** Tell the person to come back and say when the owner has added the key.

### The message to the owner

```text
Hi <owner>,

Could you give me read-only access to <owner>/<name>? I don't have a GitHub account, so this uses a
deploy key: it lets this one computer read this one repository, and nothing else.

My public key (one line):
<the ssh-ed25519 line>

To add it, either:
1. On GitHub, open the repository, then Settings, then Deploy keys, then "Add deploy key".
2. Title: <the person's first name>. Key: paste the line above.
3. Leave "Allow write access" unticked. Click "Add key".

Or, in Terminal, after saving the key to a file named key.pub:
gh repo deploy-key add key.pub --repo <owner>/<name> --title "<the person's first name>"

You can remove it at any time in the same Deploy keys list.

Thanks!
```

## Part 2 — test and clone (after the owner replies)

1. **Test the key.** Run `ssh -T git@github.com`.
   - **Success** is a reply that starts `Hi <owner>/<name>! You've successfully authenticated`. The command
     still ends with an error code; that is normal, because GitHub gives no shell.
   - **`Permission denied (publickey)`** means the key is not on the repository yet, or was added to a
     different one. Ask the person to check with the owner. Do not change the key.
2. **Clone.** `git clone git@github.com:<owner>/<name>.git ~/<name>`, unless the repository's guide names
   another folder.
3. **Updates later** need no new access: `git pull` in that folder uses the same key, for as long as the
   owner keeps it.

## Part 3 — hand over to the repository's own setup

1. **Find the guide.** Read the repository's setup guide: `docs/SETUP.md`, or the setup section of its
   `README.md`. That guide is the authority from here; this skill does not restate it.
2. **Skip what is already done.** Steps that create a GitHub account, a personal access token, or clone
   the repository are done.
3. **Do the computer's part, guide the person's part.** Run the guide's Terminal steps, explaining each
   first. For a step only the person can do (install an app, click a setting, upload a file in the Claude
   app), say exactly what to click, then wait for them to confirm.
4. **A plugin from a marketplace.** If the repository is a plugin listed in a marketplace the person
   already added, `/plugin install <plugin>@<marketplace>` now works over SSH. Follow the repository's
   guide if it says to install the skills another way (for example, uploading them in the Claude app for
   Cowork).
5. **Close.** Tell the person which app to use from now on, how updates arrive, and that the owner can
   remove the key at any time.

## When something is different

- **A `Host github.com` entry already exists.** The person probably has used GitHub before. Do not edit it.
  Explain that this skill is for a computer with no GitHub setup, and ask whether they have an account
  after all; if they do, the owner can add them as a collaborator instead.
- **The key file already exists.** Use it. If the owner never received it, send its `.pub` line again.
- **GitHub says "Key is already in use"** when the owner adds it: the same key is a deploy key on another
  repository. Make a second key named for this repository, and add a second `IdentityFile` line under the
  same `Host github.com` entry.
- **The person needs a second private repository.** Each repository needs its own key. With two
  `IdentityFile` lines, SSH tries both; `ssh -T` reports whichever repository answered first.

## Limits

- Checked 2026-11-01: a Mac with no GitHub login (no credential helper, no token) added this marketplace
  and installed the `productivity` plugin, over HTTPS. Claude Code 2.1.294's SSH check, read from the
  shipped program: it treats "successfully authenticated" as configured, refuses unknown host keys, and
  retries a failed marketplace clone over the other protocol.
- **Not run end to end:** a real deploy key added by an owner, then the test, the clone and a plugin
  install over SSH. The first real use is that test; record what happened.
- A deploy key is read-only access to one repository. It is not a GitHub account: the person cannot open
  issues, comment or see other repositories.
