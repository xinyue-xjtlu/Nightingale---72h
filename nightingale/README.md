# Nightingale — Shared Patient Record (Flask Demo)

A lightweight, role-based web app where a doctor and a nurse share one
patient record: the doctor owns the **diagnosis**, the nurse owns the
**care instructions**, and the patient gets a read-only view of their own
story plus both clinical fields. Every edit is versioned, logged in a
per-field history, and flagged to the other role as an "unseen change".

Built for the Nightingale 72-Hour Build. **All patient data is synthetic.**

---

## Features

- **Three roles, one record** — patient (read-only), doctor (diagnosis
  editor), nurse (instructions editor).
- **Three sites, three addresses, one record** — running the app starts
  one website per role (patient :5001, doctor :5002, nurse :5003). Each
  site serves only its own pages, rejects role claims it doesn't admit,
  and all three sites share the same patient record in real time.
- **Field-level ownership** — the doctor can never overwrite the nurse's
  instructions and vice versa; concurrent edits on different fields are
  fully independent.
- **Version counters + edit history** — every distinct edit bumps the
  field's version and appends `{text, time, author}` to its history; the
  full history is viewable per field.
- **Unseen-change indicators** — each role's dashboard shows a dot on any
  field the *other* role has edited since they last viewed its history;
  opening the history clears it.
- **Simulated AI suggestion** — each patient carries an `ai_suggestion`
  field shown alongside the clinical record.
- **Server-side RBAC** — role checks live in the route handlers, not in
  the templates (details below).

## Project structure

```
nightingale/
├── app.py              # Flask app: routes, edit logic, versioning, seen-state
├── data.py             # patient data source (synthetic), imported by app.py
├── ATTRIBUTION.txt     # third-party libraries and licenses
├── templates/
│   ├── login.html      # entrance chooser + per-entrance login (gated)
│   ├── patient_select.html  # patient identity claim (Tom / Tina)
│   ├── patient.html    # patient's read-only record view
│   ├── doctor.html     # doctor dashboard (diagnosis editor)
│   ├── nurse.html      # nurse dashboard (instructions editor)
│   └── history.html    # per-field edit history
└── test/
    ├── test_rbac_scope.py        # 9 role-permission tests
    └── test_concurrent_edits.py  # 7 concurrent-edit tests
```

## Quickstart

```bash
# requires Python 3.8+ and Flask
pip install flask          # if not already installed

cd nightingale
python3 app.py
# the app prints and auto-opens three sites in your browser:
```

| Site URL | Role admitted | Sees | Can edit |
|---|---|---|---|
| `http://127.0.0.1:5001` | Patient | own record only (story, diagnosis, instructions) | nothing |
| `http://127.0.0.1:5002` | Doctor | all patients, AI suggestions + edit history | diagnosis |
| `http://127.0.0.1:5003` | Nurse | all patients, AI suggestions + edit history | instructions |

Each site's login page still shows all three role cards — but claiming any
role other than the site's own is rejected by the server with an error,
and the other roles' pages do not exist on that site (404). Patients must
additionally claim their own record (Tom / Tina); opening any other
patient's record is rejected. The three sites share one in-memory patient
record: an edit made on the doctor site is immediately visible on the
nurse and patient sites.

## How RBAC is enforced

Server-side, in the route layer of each site (built by `create_app(role)`):

1. **Site-level page isolation**: each site registers only its own routes.
   `http://127.0.0.1:5001/doctor` simply does not exist — a 404, not a
   hidden button.
2. **Claim gating**: the login page shows all three role cards, but
   `/login?claim=<role>` accepts only the site's own role; anything else
   renders an error and **no session is ever created**.
3. **Session role**: a successful claim stores the role in the session
   cookie. Every protected route re-checks `session.get('role')` on every
   request; a wrong (or missing) role gets a `302` back to login.
4. **Per-site session cookies**: each site uses its own cookie name, so
   the three tabs can hold three roles simultaneously without clashing.
5. **Patient identity binding**: patients claim exactly one record
   (`/patient_claim/<id>`); `/patient/<id>` only renders when the session's
   `patient_id` matches — a patient can never open another patient's
   record.
6. **Write routes** (`POST /doctor`, `POST /nurse`) verify the role again
   before touching any field, and only ever mutate the field their role
   owns (`FIELD_KEYS` / field ownership in `app.py`).

The templates contain no permission logic — hiding a button client-side
would not protect anything; every check is verified by
`test/test_rbac_scope.py` (11 tests: per-site 404s, wrong-claim rejection
on every site, patient-to-patient isolation, three simultaneous sessions,
unauthenticated writes).

## Concurrency model

- **Different fields never clash**: the doctor editing `diagnosis` and the
  nurse editing `instructions` on the same patient at the same time are
  stored independently — each field has its own version counter and
  history.
- **Same field is last-write-wins**: a re-submission of identical text is
  ignored (no version bump, no history entry); whitespace-only edits are
  dropped.
- **Stale edits become visible, not silent**: `seen` tracks, per role, the
  last version of each field that role has looked at. If the nurse edits
  the instructions, the doctor's dashboard flags that field until the
  doctor opens its history page.

Covered by `test/test_concurrent_edits.py` (7 tests), including the
cross-role unseen-change flow.

## Data & privacy

- **Synthetic data only** — Tom and Tina are fictional.
- **No real LLM calls**: the `ai_suggestion` field is static, pre-simulated
  text stored in `data.py`. Because no patient data ever leaves the
  machine, no PHI redaction step is required in the current data flow.
  (If a real LLM were ever wired in, a redaction pipeline for names/NRICs/
  phones would have to sit in front of it — see Known limitations.)
- Session state is signed server-side via Flask's `secret_key`.

## Tests

```bash
cd nightingale
python3 -m unittest discover -s test -v
```

- `test_rbac_scope.py` — role permission matrix: each role can reach its
  own pages and is redirected away from everything else.
- `test_concurrent_edits.py` — field independence, version bumps and
  history appends, identical/empty edits ignored, and the cross-role
  unseen-change detection flow.

Tests reset the app's in-memory state (`app.reset_state()`) in `setUp`,
so they are independent of each other and of the running server.

## Known limitations

- **Site addresses are not authentication**: anyone who knows the doctor
  site URL (`:5002`) can enter as doctor. The sites enforce *which role
  each address admits* and re-check the claimed role on every request —
  but real identity verification requires usernames/passwords (or SSO),
  which is the documented next step.
- Patient identity is self-claimed at the name-picker step (no PIN);
  access is then locked to the claimed record.
- In-memory data: patients, versions and histories live in Python lists —
  they reset whenever the server restarts. A database (SQLite) is the
  obvious next step.
- The `secret_key` is a hardcoded dev value; production would load it from
  the environment.
- `app.run(debug=True)` is dev-only; production would serve via a WSGI
  server with TLS in front.
- Same-field concurrent edits are last-write-wins without an explicit
  conflict prompt.
- No real AI/LLM integration yet — connecting one requires adding a PHI
  redaction pipeline first.

## Attribution

See `ATTRIBUTION.txt` for third-party libraries (Flask, BSD-3-Clause) and
their licenses.
