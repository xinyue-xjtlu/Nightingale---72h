
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session

from data import patients


# ===== Shared state: one record per patient, shared by all three sites =====

def reset_state():
    """Re-seed the computed fields (version counters, edit histories and
    per-role last-seen versions) on top of the patients imported from
    data.py. Runs once at import; tests call it in setUp()."""
    global seen
    for p in patients:
        now = datetime.now().strftime('%m-%d %H:%M')
        p['doctor_diagnosis_version'] = 1
        p['nurse_instructions_version'] = 1
        p['doctor_diagnosis_history'] = [{"text": p['doctor_diagnosis'], "time": now, "author": "System"}]
        p['nurse_instructions_history'] = [{"text": p['nurse_instructions'], "time": now, "author": "System"}]

    # Per-role last-seen version: {role: {patient_id: {'diagnosis': v, 'instructions': v}}}
    seen = {"doctor": {}, "nurse": {}}
    for p in patients:
        for role in ("doctor", "nurse"):
            seen[role][p["id"]] = {
                "diagnosis": p["doctor_diagnosis_version"],
                "instructions": p["nurse_instructions_version"],
            }


reset_state()

# Route field name -> patient dict keys
FIELD_KEYS = {
    "diagnosis": {"history": "doctor_diagnosis_history",
                  "version": "doctor_diagnosis_version",
                  "label": "Doctor Diagnosis"},
    "instructions": {"history": "nurse_instructions_history",
                     "version": "nurse_instructions_version",
                     "label": "Nurse Instructions"},
}


def build_unseen(role):
    """{patient_id: {'diagnosis': bool, 'instructions': bool}} for one role's dashboard."""
    result = {}
    for p in patients:
        result[p["id"]] = {
            "diagnosis": p["doctor_diagnosis_version"] > seen[role][p["id"]]["diagnosis"],
            "instructions": p["nurse_instructions_version"] > seen[role][p["id"]]["instructions"],
        }
    return result


# ===== Site factory: each URL (port) serves exactly one role =====

ROLES = ("patient", "doctor", "nurse")


def create_app(site_role):
    """Builds one Flask app for one role's website.

    - The site serves ONLY its own pages; other roles' pages are 404 here.
    - The login page still shows all three role cards, but claiming a role
      that is not this site's role is rejected (session is never set).
    - Each site uses its own session cookie name, so the three browser tabs
      can hold three different roles at the same time.
    - All three sites share the same in-memory `patients` record: an edit
      made on one site is immediately visible on the others.
    """
    app = Flask(__name__)
    app.secret_key = 'nightingale-secret-key'
    app.config['SITE_ROLE'] = site_role
    app.config['SESSION_COOKIE_NAME'] = f'nightingale_{site_role}'

    # where a successful claim lands
    HOME_PATH = {'patient': '/patient', 'doctor': '/doctor', 'nurse': '/nurse'}[site_role]

    def entrance_error(claim):
        return render_template(
            'login.html', entry_role=site_role,
            error=f"This is the {site_role} site — signing in as {claim} "
                  f"here is not allowed.")

    @app.route('/')
    def index():
        if session.get('role') == site_role:
            return redirect(HOME_PATH)
        return render_template('login.html', entry_role=site_role, error=None)

    @app.route('/login')
    def login():
        claim = request.args.get('claim')
        if not claim:
            return render_template('login.html', entry_role=site_role, error=None)
        if claim != site_role:
            return entrance_error(claim)
        session['role'] = site_role
        return redirect(HOME_PATH)

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('index'))

    # ---------- patient site ----------
    if site_role == 'patient':

        @app.route('/patient')
        def patient_select():
            if session.get('role') != 'patient':
                return redirect(url_for('index'))
            return render_template('patient_select.html', patients=patients)

        @app.route('/patient_claim/<int:patient_id>')
        def patient_claim(patient_id):
            if session.get('role') != 'patient':
                return redirect(url_for('index'))
            patient = next((p for p in patients if p['id'] == patient_id), None)
            if not patient:
                return redirect(url_for('patient_select'))
            session['patient_id'] = patient_id
            return redirect(url_for('patient_dashboard', patient_id=patient_id))

        @app.route('/patient/<int:patient_id>')
        def patient_dashboard(patient_id):
            if session.get('role') != 'patient':
                return redirect(url_for('index'))
            # a patient may only open the record they claimed at login
            if session.get('patient_id') != patient_id:
                return redirect(url_for('index'))
            patient = next((p for p in patients if p['id'] == patient_id), None)
            if not patient:
                return redirect(url_for('patient_select'))
            return render_template('patient.html', patient=patient)

    # ---------- doctor site ----------
    elif site_role == 'doctor':

        @app.route('/doctor', methods=['GET', 'POST'])
        def doctor_dashboard():
            if session.get('role') != 'doctor':
                return redirect(url_for('index'))
            if request.method == 'POST':
                diagnosis = request.form.get('diagnosis', '')
                patient_id = int(request.form.get('patient_id'))
                for p in patients:
                    if p['id'] == patient_id:
                        new_text = diagnosis.strip()
                        if new_text and new_text != p['doctor_diagnosis']:
                            p['doctor_diagnosis'] = new_text
                            p['doctor_diagnosis_version'] += 1
                            p['doctor_diagnosis_history'].append({
                                'text': new_text,
                                'time': datetime.now().strftime('%m-%d %H:%M'),
                                'author': 'Doctor',
                            })
            return render_template('doctor.html', patients=patients,
                                   unseen=build_unseen('doctor'))

    # ---------- nurse site ----------
    else:

        @app.route('/nurse', methods=['GET', 'POST'])
        def nurse_dashboard():
            if session.get('role') != 'nurse':
                return redirect(url_for('index'))
            if request.method == 'POST':
                instruction = request.form.get('instruction', '')
                patient_id = int(request.form.get('patient_id'))
                for p in patients:
                    if p['id'] == patient_id:
                        new_text = instruction.strip()
                        if new_text and new_text != p['nurse_instructions']:
                            p['nurse_instructions'] = new_text
                            p['nurse_instructions_version'] += 1
                            p['nurse_instructions_history'].append({
                                'text': new_text,
                                'time': datetime.now().strftime('%m-%d %H:%M'),
                                'author': 'Nurse',
                            })
            return render_template('nurse.html', patients=patients,
                                   unseen=build_unseen('nurse'))

    # ---------- history (doctor & nurse sites only) ----------
    if site_role in ('doctor', 'nurse'):

        @app.route('/history/<int:patient_id>/<field>')
        def history(patient_id, field):
            if session.get('role') != site_role:
                return redirect(url_for('index'))
            dashboard = '/doctor' if site_role == 'doctor' else '/nurse'
            if field not in FIELD_KEYS:
                return redirect(dashboard)
            patient = next((p for p in patients if p['id'] == patient_id), None)
            if not patient:
                return redirect(dashboard)
            cfg = FIELD_KEYS[field]
            seen[site_role][patient_id][field] = patient[cfg['version']]
            return render_template('history.html',
                                   patient=patient,
                                   field_label=cfg['label'],
                                   entries=list(reversed(patient[cfg['history']])),
                                   back_url=dashboard)

    return app


patient_app = create_app('patient')
doctor_app = create_app('doctor')
nurse_app = create_app('nurse')


if __name__ == '__main__':
    import threading
    import time
    import webbrowser

    SITES = [
        ('patient', patient_app, 5001),
        ('doctor', doctor_app, 5002),
        ('nurse', nurse_app, 5003),
    ]
    print('Nightingale — three sites, one shared patient record:')
    for role, app_instance, port in SITES:
        url = f'http://127.0.0.1:{port}'
        print(f'  {role:<8} {url}')
        threading.Thread(
            target=app_instance.run,
            kwargs={'host': '127.0.0.1', 'port': port,
                    'debug': False, 'use_reloader': False},
            daemon=True,
        ).start()

    for _, _, port in SITES:
        webbrowser.open(f'http://127.0.0.1:{port}')

    print('(all three sites opened in your browser — Ctrl+C to stop)')
    while True:
        time.sleep(3600)
