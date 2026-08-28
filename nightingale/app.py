
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = 'nightingale-secret-key'

# ===== Data (single source of truth: data.py) =====
from data import patients

# Seed edit history + version counters (also re-run by tests for a clean slate)
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

# ===== Routes =====

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/login')
def do_login():
    role = request.args.get('role')
    if role:
        session['role'] = role
        if role == 'patient':
            return redirect(url_for('patient_select'))
        elif role == 'doctor':
            return redirect(url_for('doctor_dashboard'))
        elif role == 'nurse':
            return redirect(url_for('nurse_dashboard'))
    return redirect(url_for('login'))

@app.route('/patient')
def patient_select():
    if session.get('role') != 'patient':
        return redirect(url_for('login'))
    return render_template('patient_select.html', patients=patients)

@app.route('/patient/<int:patient_id>')
def patient_dashboard(patient_id):
    if session.get('role') != 'patient':
        return redirect(url_for('login'))
    patient = None
    for p in patients:
        if p['id'] == patient_id:
            patient = p
            break
    if not patient:
        return redirect(url_for('patient_select'))
    return render_template('patient.html', patient=patient)

@app.route('/doctor', methods=['GET', 'POST'])
def doctor_dashboard():
    if session.get('role') != 'doctor':
        return redirect(url_for('login'))
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
    return render_template('doctor.html', patients=patients, unseen=build_unseen('doctor'))

@app.route('/nurse', methods=['GET', 'POST'])
def nurse_dashboard():
    if session.get('role') != 'nurse':
        return redirect(url_for('login'))
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
    return render_template('nurse.html', patients=patients, unseen=build_unseen('nurse'))

@app.route('/history/<int:patient_id>/<field>')
def history(patient_id, field):
    role = session.get('role')
    if role not in ('doctor', 'nurse'):
        return redirect(url_for('login'))
    dashboard = url_for('doctor_dashboard') if role == 'doctor' else url_for('nurse_dashboard')
    if field not in FIELD_KEYS:
        return redirect(dashboard)
    patient = next((p for p in patients if p['id'] == patient_id), None)
    if not patient:
        return redirect(dashboard)
    cfg = FIELD_KEYS[field]
    seen[role][patient_id][field] = patient[cfg['version']]  # mark seen, clears dot
    return render_template('history.html',
                           patient=patient,
                           field_label=cfg['label'],
                           entries=list(reversed(patient[cfg['history']])),
                           back_url=dashboard)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
