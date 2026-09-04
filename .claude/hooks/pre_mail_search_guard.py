"""PreToolUse hook (mcp__*Gmail*search_threads): block sender-limited mail searches.

Why this exists (2026-08-21..24, Soulful-Content / Freeasy):
A monitoring query pinned the search to three known sender addresses
(operation-r@ / f-project@ / freeasy@ ibridge). The delivery-start notice
arrived from a fourth address -- the sales rep's personal mailbox
(niu_keiji@ibridge.jp) -- so it never matched. "0 results" was then reported
as "no change" for FOUR CONSECUTIVE DAYS, twice after the user explicitly
asked "are you sure?".

The rule this encodes:
    Filter mail by WHO YOU ARE LOOKING FOR (the counterparty: domain, brand,
    subject), never by WHICH DESK HAPPENS TO SEND IT.
A counterparty sends from system addresses, operations addresses, and
individual staff mailboxes interchangeably. Enumerating senders is a
guess about someone else's org chart, and a silent one: it fails by
returning zero, which is indistinguishable from good news.

Trigger: a query whose sender terms are ALL narrower than a bare domain,
i.e. every from:/to: names a full mailbox (user@host) and the query carries
no domain-level or keyword fallback. Searching `from:@ibridge.jp` or
`from:ibridge.jp` is fine -- that is domain-level. Adding a bare keyword
(e.g. `ibridge OR Freeasy`) alongside is also fine, since the keyword
still matches mail from unknown senders.

Deliberately NOT blocked:
  - Searches for a specific person on purpose ("did Yoshida reply?") --
    these normally carry one from: and no monitoring intent, so we only
    warn when there are 2+ pinned mailboxes, which is the signature of an
    enumerated-desk allowlist.
  - label:/in:/after: only queries, threads by id, etc.

Fail-open: any error -> exit 0. JSON deny only (never exit 2).
Deployed from claude-governance/templates/hooks/ -- edit there, not here.

CALIBRATION (measured 2026-09-04, not chosen)
---------------------------------------------
Fired on 14 of 40 real Gmail calls replayed from 27 production
transcripts = 35.00%. The denominator of 40 is small, so the confidence
interval around this rate is wide and the point estimate should not be
over-trusted. Gmail search volume overall is low relative to other tools
(40 calls vs. thousands of Bash/Edit/Read calls across the same
transcripts), which limits the real-world blast radius of a high rate,
but re-measurement against a larger sample of Gmail calls is needed
before treating 35.00% as a stable estimate of this guard's true firing
rate.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

# A from:/to: clause, including the grouped form  from:(a@x OR b@y OR c@z).
# The whole group must be captured -- matching only the first address made an
# enumerated 3-sender allowlist look like a single targeted lookup, which is
# precisely how the 2026-08-21 query slipped through an earlier version.
_SENDER_CLAUSE = re.compile(r"\b(?:from|to)\s*:\s*(\([^)]*\)|[^\s()]+)", re.I)
# A full mailbox (user@host) anywhere inside a sender clause -> too narrow.
_MAILBOX = re.compile(r"[^\s()]+@[^\s()]+")
# A sender term naming only a domain (ibridge.jp / @ibridge.jp) -> broad enough.
_DOMAIN_ONLY = re.compile(r"(?<!\S)@?([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?!\S)")

# subject:<term> counts as a content term -- it matches words in the mail
# itself, so it survives a change of sender. label:/in:/after: do not:
# they are metadata the counterparty does not control.
_SUBJECT = re.compile(r"\bsubject\s*:\s*\(?\s*\S", re.I)

_OPERATORS = re.compile(
    r"\b(?:from|to|cc|bcc|subject|label|in|is|has|after|before|newer|older|"
    r"newer_than|older_than|filename|list|category|deliveredto|rfc822msgid|"
    r"larger|smaller|size)\s*:\S*",
    re.I,
)


def _bare_keywords(query):
    """Terms that are not operators -- these still match unknown senders.

    Sender clauses are removed WHOLE first. Stripping only `from:` off
    `from:(a@x OR b@y)` would leave b@y looking like a free-text keyword,
    which would wrongly satisfy the keyword-fallback escape hatch.
    """
    stripped = _SENDER_CLAUSE.sub(" ", query)
    stripped = _OPERATORS.sub(" ", stripped)
    stripped = re.sub(r"[(){}\[\]\"]", " ", stripped)
    return [
        t
        for t in stripped.split()
        if t.upper() not in ("OR", "AND", "-") and len(t) > 1 and "@" not in t
    ]


def main():
    # repo-local copy wins, so a project can override this guard
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(
            os.path.join(os.getcwd(), ".claude", "hooks", os.path.basename(__file__))
        )
        if me != local and os.path.exists(local):
            return
    except Exception:
        pass

    try:
        try:
            sys.stdin.reconfigure(encoding="utf-8")
        except Exception:
            pass
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", "replace"))

        tool = (data.get("tool_name") or "")
        if "gmail" not in tool.lower():
            return
        if "search" not in tool.lower() and "list" not in tool.lower():
            return

        query = ((data.get("tool_input") or {}).get("query") or "")
        if not query.strip():
            return

        clauses = _SENDER_CLAUSE.findall(query)

        mailboxes = []
        has_domain_level = False
        for clause in clauses:
            inner = clause.strip()
            if inner.startswith("("):
                inner = inner[1:-1] if inner.endswith(")") else inner[1:]
            found = _MAILBOX.findall(inner)
            mailboxes.extend(found)
            # any bare term in the clause that is a domain rather than a mailbox
            for term in re.split(r"\s+|\bOR\b|\bAND\b", inner, flags=re.I):
                term = term.strip().strip("(),")
                if term and "@" not in term.lstrip("@") and _DOMAIN_ONLY.fullmatch(term):
                    has_domain_level = True

        domains = []
        for m in mailboxes:
            d = m.split("@")[-1].strip().rstrip(")>,;")
            if d and d not in domains:
                domains.append(d)
        for clause in clauses:
            for term in re.split(r"\s+|\bOR\b|\bAND\b", clause.strip("()"), flags=re.I):
                term = term.strip().strip("(),@")
                if term and "@" not in term and _DOMAIN_ONLY.fullmatch(term):
                    if term not in domains:
                        domains.append(term)
        suggestion = " OR ".join(sorted(domains)) if domains else "<counterparty>"

        has_content = bool(_bare_keywords(query)) or bool(_SUBJECT.search(query))

        # A search for ONE named individual is a targeted lookup ("did Yoshida
        # reply?"), not counterparty monitoring. Requiring a brand term there
        # would be noise, so exempt it -- but only for a single mailbox, since
        # two or more is the signature of an enumerated-desk allowlist.
        if len(mailboxes) == 1 and not has_domain_level:
            return

        # CHECK 2 -- sender-only search, no content term.
        # Empirically (8/8 Freeasy mails, 4 distinct senders, 2026-08-18..25)
        # the service name appears in every subject or body. A brand/company
        # term therefore survives sender changes, outsourced senders, and
        # forwards, which a from: filter of any width does not.
        if not has_content:
            # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
            _record_firing("pre_mail_search_guard", data)
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": (
                                "MAIL SEARCH HAS NO CONTENT TERM: this query filters only by "
                                "sender/metadata, so it can only find mail from mailboxes you "
                                "already know about. If the counterparty adds a desk, uses an "
                                "outsourced sender, or someone forwards the notice, this query "
                                "returns 0 -- indistinguishable from 'nothing arrived'.\n\n"
                                "Add the service or company name, which rides in the subject or "
                                "body regardless of who sent it:\n"
                                "    <ServiceName> OR <CompanyName>"
                                + (" OR " + suggestion if suggestion != "<counterparty>" else "")
                                + " after:YYYY/MM/DD\n"
                                "or keep the sender filter and OR a content term onto it.\n\n"
                                "Verified 2026-08-25: all 8 Freeasy mails across 4 different "
                                "sender addresses carried the service name; the one missed for "
                                "4 days had it in the subject line."
                            ),
                        }
                    }
                )
            )
            return

        if len(mailboxes) < 2:
            return  # one named person is a normal lookup, not an allowlist
        if has_domain_level:
            return  # a domain-level sender term is already broad enough
        if has_content:
            # A content term ORed alongside the senders means mail from an
            # unknown desk still matches, so the allowlist is not load-bearing
            # and cannot cause the silent-zero failure this guard exists for.
            return

        # CHECK 1 -- enumerated sender allowlist (the 2026-08-21 failure).
        reason = (
            "MAIL SEARCH TOO NARROW: this query pins the sender to "
            + str(len(mailboxes))
            + " specific mailboxes ("
            + ", ".join(mailboxes[:4])
            + "). A counterparty also writes from system addresses and from "
            "individual staff mailboxes, so an enumerated sender list silently "
            "misses mail -- it fails by returning 0 results, which looks "
            "identical to 'nothing arrived'.\n\n"
            "This exact failure happened 2026-08-21..24: a delivery-start "
            "notice came from a sales rep's personal address that was not in "
            "the 3-address allowlist, and 'no change' was reported for four "
            "days straight.\n\n"
            "Search by WHO YOU ARE LOOKING FOR, not by which desk sent it:\n"
            "    " + suggestion + " after:YYYY/MM/DD\n"
            "Domain-level (from:" + (domains[0] if domains else "example.com") + ") "
            "or a bare keyword alongside the from: terms also passes this check.\n\n"
            "If you report 0 results from a narrowed query, you must write "
            "'no mail from THESE senders -- others unchecked', never 'no change'."
        )

        # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
        _record_firing("pre_mail_search_guard", data)
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }
            )
        )
    except Exception:
        return  # fail-open: never block work because the guard itself broke


if __name__ == "__main__":
    main()
