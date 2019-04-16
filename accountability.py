from flask import Flask, session, redirect, url_for, request, render_template, jsonify
import random
import base64
import sqlite3
import sqlalchemy
from flask import g
import hashlib
import time
import os
import urllib.parse

# App setup
app = Flask(__name__)
app.secret_key = b'\xbfEdVSb\xc6\x91Q\x02\x1c\xa7cN\xba$'
app.dev = False

# Default directories and values
DATABASE = './database.db'
IMAGE_DIR = 'static/images/'
NUM_IMAGES = 10
NON_POLITICAL_IMG_PERCENTAGE = 0.1
TIMEOUT = 20
WORK_PAGE_ACTIVITY_TIMER = 8
WAIT_PAGE_ACTIVITY_TIMER = 8
DEV = False

# Page URLs
WAIT_PAGE = 'wait'
DASHBOARD_PAGE = 'dashboard'
SUBMIT_MODS_PAGE = 'submit_mods'
SUBMIT_OBS_PAGE = 'submit_obs'
WORK_PAGE = 'work'
DONE_PAGE = 'done'
NARRATIVE_PAGE = 'narrative'
CONSENT_PAGE = 'consent'
EXPERIMENT_COMPLETE_PAGE = 'experiment_complete'
POLL_WORK_READY_PAGE = 'poll_work_ready'
MARK_WORK_READY_PAGE = 'mark_work_ready'
POLITIC_PAGE = 'political_affiliation'

# Get parameters in URL
TURK_ID_VAR = 'workerId'
ASSIGNMENT_ID_VAR = 'assignmentId'
CONSENT_VAR = 'consent'
JOB_VAR = 'j'
CONDITION_VAR = 'c'
WAS_OBSERVER_VAR = 'was_observer'
IS_LAST_VAR = 'isLast'
WAS_WAITING_VAR = 'was_waiting'

# Possible values for Get parameters
JOB_MOD_VAL = 'mod'
JOB_OBS_VAL = 'obs'
CONDITION_CON_VAL = 'con'
CONDITION_EXP_VAL = 'exp'

# User colors
RED = '#ff0000'
BLUE = '#0000ff'
GRAY = '#888888'

# App initialization
@app.before_first_request
def build_db():
    print('Initializing app...')
    db = get_db()

    # Load database schema
    db.execute(sqlalchemy.text('create table if not exists images (img_id serial primary key, path text unique, text text, poster text, affiliation text);'))
    db.execute(sqlalchemy.text('create table if not exists participants (user_id serial primary key, turk_id text unique, condition text, edge_case text, disconnected boolean, political_affiliation text, randomized_affiliation text, was_waiting boolean, work_complete boolean);'))
    db.execute(sqlalchemy.text('create table if not exists pairs (id serial primary key, obs_id integer unique references participants(user_id), mod_id integer unique references participants(user_id), obs_submitted boolean, mod_submitted boolean, work_ready boolean, mod_ready boolean, obs_ready boolean, last_mod_time decimal, last_obs_time decimal, last_mod_wait decimal, last_obs_wait decimal, disconnect_occurred boolean, create_time numeric, restarted boolean);'))
    db.execute(sqlalchemy.text('create table if not exists observations(id serial primary key, pair_id integer references pairs(id), obs_text text, img_id integer, agreement_text text);'))
    db.execute(sqlalchemy.text('create table if not exists moderations(id serial primary key, decision text, img_id integer references images(img_id), pair_id integer references pairs(id));'))
    db.execute(sqlalchemy.text('create table if not exists chosen_imgs(id serial primary key, img_id integer, pair_id integer);'))
    db.execute(sqlalchemy.text('create table if not exists control_imgs(id serial primary key, img_id integer, turk_id text);'))
    db.execute(sqlalchemy.text('create table if not exists images_revealed(id serial primary key, pair_id integer, img_index integer, temp_decision text);'))
    db.execute(sqlalchemy.text('create table if not exists consent(id serial primary key, turk_id text unique, response text);'))
    db.execute(sqlalchemy.text('create table if not exists exp_complete(id serial primary key, complete boolean unique);'))
    db.execute(sqlalchemy.text('create table if not exists mod_forms(id serial primary key, turk_id text unique, curr_index integer, responses text);'))

    # Load images (if none are loaded)
    out = db.execute('select count(*) from images')
    count = out.fetchall()[0][0]
    if count == 0:
        load_images_to_db()

# Close database
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    # if db is not None:
        # db.close()

# Get database reference
def get_db():
    db = getattr(g, '_database', None)
    if db is None: # Launch database if it hasn't been
        db = g._database = sqlalchemy.create_engine(os.environ['DATABASE_URL'], pool_size = 15)
    return db

# Set db variable on launch
with app.app_context():
    db = get_db()

# Query database
def query_db(query, args=(), one=False):
    cur = get_db().execute(sqlalchemy.text(query), list(args))
    rv = cur.fetchall()
    # get_db().commit()
    cur.close()
    return (rv[0] if rv else None) if one else rv

# Load image paths from images folder to database
def load_images_to_db():
    conn = db.raw_connection()
    cur = conn.cursor()
    f = open('./images_table.csv', 'rb')
    cur.copy_expert('COPY images (path, text, poster, affiliation) from STDIN WITH CSV HEADER', f)
    conn.commit()

# Gets subset of all images to be displayed
def get_array_subset(array, num_vals, cannot_contain):
    assert len(array) - len(cannot_contain) >= num_vals
    assert NUM_IMAGES > 0

    # Separating political from non-political images
    pol_imgs = []
    non_pol_imgs = []
    for i in range(len(array)):
        if array[i][1] == 'n':
            non_pol_imgs.append(array[i])
        else:
            pol_imgs.append(array[i])

    subset = []

    # Non-political images (at least 1)
    num_non_political = max(round(NUM_IMAGES * NON_POLITICAL_IMG_PERCENTAGE), 1)
    while len(subset) < num_non_political:
        i = random.randint(0, len(non_pol_imgs) - 1)
        val = non_pol_imgs[i]

        if val not in subset and val not in cannot_contain:
            subset.append(val)

    # Political images
    while len(subset) < num_vals: # Add num_vals images
        i = random.randint(0, len(pol_imgs) - 1)
        val = pol_imgs[i]

        # Don't add image if it was already seen previously in observer role
        if val not in subset and val not in cannot_contain:
            subset.insert(random.randrange(len(subset) + 1), val)

    return subset

# Calculates current state of worker
def get_current_worker_state(turk_id, last_wait_time, last_work_time):
    if turk_id is not None and db.execute(sqlalchemy.text('select work_complete from participants where turk_id=:turk_id'), turk_id=turk_id).fetchone()[0] is not None:
        return 'Done'
    elif turk_id is not None and db.execute(sqlalchemy.text('select disconnected from participants where turk_id=:turk_id'), turk_id=turk_id).fetchone()[0] is not None:
        return 'Disconnected'
    elif last_wait_time is not None and last_work_time is not None:
        if last_wait_time < last_work_time and last_wait_time < WAIT_PAGE_ACTIVITY_TIMER:
            return 'Waiting'
        elif last_work_time < WORK_PAGE_ACTIVITY_TIMER:
            return 'Working'
        else:
            return 'Unresponsive'
    else:
        return 'Unknown'

# Dashboard colors corresponding to displayed worker states
def get_worker_status_color(state):
    if state == 'Waiting':
        return 'brown'
    elif state == 'Working':
        return 'blue'
    elif state == 'Unresponsive':
        return 'yellow'
    elif state == 'Disconnected':
        return 'red'
    elif state == 'Done':
        return 'green'
    else:
        return 'white'

# Dashboard page
@app.route('/' + DASHBOARD_PAGE)
def dashboard():
    # Get workers in control group and pairs in experimental group
    participants=db.execute(sqlalchemy.text('select * from participants order by user_id asc')).fetchall()
    control = [p for p in participants if p[2] == CONDITION_CON_VAL]
    pairs = db.execute(sqlalchemy.text('select * from pairs order by id asc')).fetchall()

    done_class = 'class="worker-done"' # Class that marks worker/pair as finished on dashboard

    # Construct control table elements
    control_html = ''
    for c in control:
        worker_id = c[1]
        worker_done = db.execute(sqlalchemy.text('select work_complete from participants where turk_id=:worker_id'), worker_id=worker_id).fetchone()[0] is not None
        done_text = done_class if worker_done else ''
        control_html += '<tr><th {} scope="row">{}</th><td {}>{}</td></tr>'.format(done_text, c[0], done_text, worker_id)

    complete = db.execute(sqlalchemy.text('select complete from exp_complete')).fetchone()
    experiment_complete = complete is not None and complete[0] is not None

    # Construct experimental table elements
    experiment_html = ''
    for p in pairs:
        pair_id = p[0]
        obs_id = p[1]
        mod_id = p[2]

        # get the turk_ids for moderator and paired observer
        if mod_id is None:
            mod_turk = ''
        else:
            mod_turk = db.execute(sqlalchemy.text('select turk_id from participants where user_id=:mod_id'), mod_id=mod_id).fetchone()[0]

        if obs_id is None:
            obs_turk = ''
        else:
            obs_turk = db.execute(sqlalchemy.text('select turk_id from participants where user_id=:obs_id'), obs_id=obs_id).fetchone()[0]

        mod_done = db.execute(sqlalchemy.text('select mod_submitted from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0] is not None
        obs_done = db.execute(sqlalchemy.text('select obs_submitted from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0] is not None
        done_text = done_class if mod_done and obs_done or mod_done and obs_turk == '' or mod_turk == '' and obs_done else ''
        work_ready = db.execute(sqlalchemy.text('select work_ready from pairs where id=:pair_id'), pair_id=pair_id).fetchone()
        restarted = p[14] is not None
        restart_style = 'background-color: red;' if restarted else ''
        
        work_ready_btn = '<button ' + ('disabled' if work_ready[0] is not None else '') + ' onclick="markPairWorking(\'' + str(pair_id) + '\', this)">Start Work</button>'
        unpaired_mod = mod_turk != '' and obs_turk == ''
        unpaired_obs = mod_turk == '' and obs_turk != ''
        if (unpaired_mod or unpaired_obs) and not experiment_complete and not restarted:
            work_ready_btn = ''

        mod_id_text = mod_turk
        obs_id_text = obs_turk
        
        disconnect_style = '' if p[12] is None else 'opacity: 0.25; pointer-events: none;'
        
        # Status information
        
        # Last wait page ping
        time_now = time.time()
        last_mod_wait_data = None if mod_turk == '' else db.execute(sqlalchemy.text('select last_mod_wait from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]
        last_mod_wait_time = None if last_mod_wait_data is None else round(time_now - float(last_mod_wait_data), 1)
        last_obs_wait_data = None if obs_turk == '' else db.execute(sqlalchemy.text('select last_obs_wait from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]
        last_obs_wait_time = None if last_obs_wait_data is None else round(time_now - float(last_obs_wait_data), 1)
        last_mod_wait = None if last_mod_wait_time is None else str(last_mod_wait_time) + ' seconds ago'
        last_obs_wait = None if last_obs_wait_time is None else str(last_obs_wait_time) + ' seconds ago'
        
        # Last work page ping
        last_mod_work_ping_data = None if mod_turk == '' else db.execute(sqlalchemy.text('select last_mod_time from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]
        last_mod_work_ping_time = None if last_mod_work_ping_data is None else round(time_now - float(last_mod_work_ping_data), 1)
        last_obs_work_ping_data = None if obs_turk == '' else db.execute(sqlalchemy.text('select last_obs_time from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]
        last_obs_work_ping_time = None if last_obs_work_ping_data is None else round(time_now - float(last_obs_work_ping_data), 1)
        last_mod_work_ping = None if last_mod_work_ping_time is None else str(last_mod_work_ping_time) + ' seconds ago'
        last_obs_work_ping = None if last_obs_work_ping_time is None else str(last_obs_work_ping_time) + ' seconds ago'
        
        # Worker states
        mod_state = '' if mod_turk == '' else get_current_worker_state(mod_turk, last_mod_wait_time, last_mod_work_ping_time)
        obs_state = '' if obs_turk == '' else get_current_worker_state(obs_turk, last_obs_wait_time, last_obs_work_ping_time)
        mod_state_color = get_worker_status_color(mod_state)
        obs_state_color = get_worker_status_color(obs_state)
        
        # Number of images revealed
        images_revealed_data = db.execute(sqlalchemy.text('select * from images_revealed where pair_id=:pair_id'), pair_id=pair_id).fetchall()
        images_revealed = 0 if images_revealed_data is None else len(images_revealed_data)
        
        # Edge cases
        mod_edge_case = '' if mod_turk == '' else db.execute(sqlalchemy.text('select edge_case from participants where turk_id=:mod_id'), mod_id=mod_turk).fetchone()[0]
        obs_edge_case = '' if obs_turk == '' else db.execute(sqlalchemy.text('select edge_case from participants where turk_id=:obs_id'), obs_id=obs_turk).fetchone()[0]
        
        # Building status blocks
        mod_status_text = '' if mod_turk == '' else '<p style="margin-top:10px; font-size:10px;"><strong>State:</strong> <span style="color:{};">{}</span><br /><strong>Last wait ping:</strong> {}<br /><strong>Last work ping:</strong> {}<br /><strong>Images revealed:</strong> {}/{}<br/ ><strong>Edge case:</strong> {}</p>'.format(mod_state_color, mod_state, last_mod_wait, last_mod_work_ping, images_revealed, NUM_IMAGES, mod_edge_case)
        obs_status_text = '' if obs_turk == '' else '<p style="margin-top:10px; font-size:10px;"><strong>State:</strong> <span style="color:{};">{}</span><br /><strong>Last wait ping:</strong> {}<br /><strong>Last work ping:</strong> {}<br /><strong>Images revealed:</strong> {}/{}<br/ ><strong>Edge case:</strong> {}</p>'.format(obs_state_color, obs_state, last_obs_wait, last_obs_work_ping, images_revealed, NUM_IMAGES, obs_edge_case)
        
        experiment_html += '<tr style="{}{}"><th {} scope="row">{}{}</th><td {}>{}{}</td><td {}>{}{}</td></tr>'.format(disconnect_style, restart_style, done_text, pair_id, work_ready_btn, done_text, mod_id_text, mod_status_text, done_text, obs_id_text, obs_status_text)
        
    num_pairs = len(db.execute(sqlalchemy.text('select * from pairs')).fetchall())
    
    return render_template('dashboard.html', control_html=control_html, experiment_html=experiment_html, experiment_complete=experiment_complete, num_pairs=num_pairs)

# Marks pair as ready to be moved to work page
@app.route("/" + MARK_WORK_READY_PAGE, methods=['POST'])
def mark_work_ready():
    json = request.json
    pair_id = json['pair_id']
    print('{}: setting work_ready=true in pairs where pair_id={}'.format(MARK_WORK_READY_PAGE, pair_id))
    db.execute(sqlalchemy.text('update pairs set work_ready=:true where id=:pair_id'), true=True, pair_id=pair_id)
    return jsonify(status='success')

# Mark experiment as completed on dashboard page
@app.route("/" + EXPERIMENT_COMPLETE_PAGE, methods=['POST'])
def experiment_finished():
    db.execute(sqlalchemy.text('insert into exp_complete(complete) VALUES(:complete)'), complete=True)

    unpaired_mods = db.execute(sqlalchemy.text('select mod_id from pairs where obs_id is null')).fetchall()
    for mod_id in unpaired_mods:
        print('{}: setting edge_case=Last in participants where user_id={}'.format(EXPERIMENT_COMPLETE_PAGE, mod_id[0]))
        db.execute(sqlalchemy.text('update participants set edge_case=:last where user_id=:mod_id'), last='Last', mod_id=mod_id[0])

    return jsonify(status='success')

# Restart experimental condition
@app.route('/restart_experimental', methods=['POST'])
def restart_experimental():
    # Mark all current pairs restarted
    db.execute(sqlalchemy.text('update pairs set restarted=TRUE'))
    
    # Set all currently unpaired moderators to 'Last' edge case
    unpaired_mods = db.execute(sqlalchemy.text('select mod_id from pairs where mod_id is not null and obs_id is null')).fetchall()
    for unpaired in unpaired_mods:
        db.execute(sqlalchemy.text('update participants set edge_case=:last where user_id=:unpaired'), last='Last', unpaired=unpaired[0])
    
    return jsonify(status='success')

# Narrative page
@app.route("/" + NARRATIVE_PAGE)
def narrative():
    session.clear()

    turkId = request.args.get(TURK_ID_VAR)
    assignmentId = request.args.get(ASSIGNMENT_ID_VAR)

    preview = False
    if turkId is None:
        preview = True
    else:
        session[TURK_ID_VAR] = turkId
        session[ASSIGNMENT_ID_VAR] = assignmentId
        session[WAS_WAITING_VAR] = None

    return render_template('narrative.html', turkId=turkId, preview=preview, num_images = NUM_IMAGES, dev=('true' if DEV else 'false'))

# Consent page
@app.route("/" + CONSENT_PAGE)
def consent():
    turkId = session[TURK_ID_VAR]
    print('{}: inserting turk_id={} and response=No in consent'.format(CONSENT_PAGE, turkId))
    db.execute(sqlalchemy.text('insert into consent(turk_id, response) VALUES(:turk_id, :no)'), turk_id=turkId, no='No')
    return render_template('consent.html')

# Done page
@app.route("/" + DONE_PAGE)
def done():
    turk_id = session.get(TURK_ID_VAR)
    consent = request.args.get(CONSENT_VAR)
    
    if consent == 'Yes' or consent == 'pilot':
        print('{}: updating consent response=Yes where turk_id={}'.format(DONE_PAGE, turk_id))
        db.execute(sqlalchemy.text('update consent set response=:consent where turk_id=:turk_id'), consent=consent, turk_id=turk_id)
    
    db.execute(sqlalchemy.text('update participants set work_complete=:complete where turk_id=:turk_id'), complete=True, turk_id=turk_id)
    return render_template('done.html', turk_id=turk_id, task_finished=True, assignment_id=session[ASSIGNMENT_ID_VAR])

# returns True if the person got paired, or False if a new pair was created
def check_edge_case(user_id):
    obs_ids = db.execute(sqlalchemy.text('select obs_id from pairs where mod_id IS NULL and restarted IS NULL')).fetchall()
    paired = False
    if obs_ids is not None:
        for obs_id in obs_ids: # Trying to pair with an existing observer
            edge_case = db.execute(sqlalchemy.text('select edge_case from participants where user_id=:obs_id'), obs_id=obs_id[0]).fetchone() # Checking if observer finished task unpaired
            if edge_case is not None and edge_case[0] != 'Unpaired observer':
                print('check_edge_case: set mod_id={} where obs_id={} in pairs'.format(user_id, obs_id[0]))
                db.execute(sqlalchemy.text('update pairs set mod_id=:uid where obs_id=:obs_id'), uid=user_id, obs_id=obs_id[0]) # Pairing worker
                paired = True
                break
    if not paired:
        print('check_edge_case: insert mod_id={} and create_time={} into pairs'.format(user_id, time.time()))
        db.execute(sqlalchemy.text('insert into pairs(mod_id, create_time) VALUES(:uid, :time)'), uid=user_id, time=time.time()) # Creating new pair

    return paired

#@app.route("/" + POLITIC_PAGE, methods=['POST'])
#def political_affiliation():
#    json = request.json
#    results = db.execute(sqlalchemy.text('update participants set political_affiliation=:politics where turk_id=:turk_id'), politics=json['political'], turk_id = json['turk_id'])
#
#    return jsonify(status='success')


# Wait page
@app.route("/" + WAIT_PAGE)
def wait():
    print(str(session))
    uid = session[TURK_ID_VAR]
    pid = 0
    
    # Checking if user is trying to rejoin after a disconnect
    disconnected = db.execute(sqlalchemy.text('select disconnected from participants where turk_id=:turk_id'), turk_id=uid).fetchone()
    if disconnected is not None and disconnected[0] is not None:
        return redirect('/disconnect?turkId=%s&dc=you' % uid)
    
    # Check if user has already finished their task, moving them directly to Done page if so
    work_complete = db.execute(sqlalchemy.text('select work_complete from participants where turk_id=:turk_id'), turk_id=uid).fetchone()
    if work_complete is not None and work_complete[0] is not None:
        return redirect('/done?consent=pilot')
    
    # Experiment is finished and user doesn't need to wait
    exists = db.execute(sqlalchemy.text('select * from participants where turk_id=:uid'), uid=uid).fetchone()
    worker_exists = exists is not None

    complete = db.execute(sqlalchemy.text('select complete from exp_complete')).fetchone()
    experiment_complete = complete is not None and complete[0] is not None
    if experiment_complete and not worker_exists:
        return render_template('done.html', turk_id=uid, task_finished=False)

    # Checking if worker was already on the wait page (i.e. a refresh occurred)
    was_waiting = db.execute(sqlalchemy.text('select was_waiting from participants where turk_id=:uid'), uid=uid).fetchone()
    if was_waiting is not None and was_waiting[0] is not None:
        session[WAS_WAITING_VAR] = True
        user_id = db.execute(sqlalchemy.text('select user_id from participants where turk_id=:uid'), uid=uid).fetchone()[0]

        cond = db.execute(sqlalchemy.text('select condition from participants where turk_id=:uid'), uid=uid).fetchone()[0]
        session[CONDITION_VAR] = cond
        session['pid'] = user_id

        if cond == CONDITION_CON_VAL:
            session[JOB_VAR] = JOB_MOD_VAL
            return redirect(url_for(WORK_PAGE))

        pair_check = db.execute(sqlalchemy.text('select id from pairs where mod_id=:user_id'), user_id=user_id).fetchone()
        if pair_check is not None and pair_check[0] is not None:
            session[JOB_VAR] = JOB_MOD_VAL
        else:
            session[JOB_VAR] = JOB_OBS_VAL
        job = session[JOB_VAR]

        if job == JOB_MOD_VAL:
            output = db.execute(sqlalchemy.text('select id, create_time from pairs where mod_id=:uid'), uid=user_id).fetchone()
            pair_id = output[0]
            create_time = output[1]
        else:
            output = db.execute(sqlalchemy.text('select id, create_time from pairs where obs_id=:uid'), uid=user_id).fetchone()
            pair_id = output[0]
            create_time = output[1]
        return render_template('wait.html', pair_id=pair_id, room_name='pair-{}-{}'.format(pair_id, create_time), role=job)
    else:
        existing_worker = db.execute(sqlalchemy.text('select user_id from participants where turk_id=:uid'), uid=uid).fetchone()
        if existing_worker is not None:
            db.execute(sqlalchemy.text('update participants set was_waiting=:was_waiting where turk_id=:uid'), was_waiting=True, uid=uid)
        session[WAS_WAITING_VAR] = True

    was_observer = session.get(WAS_OBSERVER_VAR)
    session[WAS_OBSERVER_VAR] = None

    # Exiting early if worker has already been added to system
    pid = db.execute(sqlalchemy.text('select user_id from participants where turk_id=:uid'), uid=uid).fetchone()
    worker_exists = pid is not None
    if worker_exists:
        pid = pid[0]
    
    # Experimental worker rejoining after closing page
    if worker_exists and not was_observer:
        condition = db.execute(sqlalchemy.text('select condition from participants where turk_id=:uid'), uid=uid).fetchone()[0]
        if condition != CONDITION_CON_VAL:
            session[CONDITION_VAR] = CONDITION_EXP_VAL
            user_id = db.execute(sqlalchemy.text('select user_id from participants where turk_id=:uid'), uid=uid).fetchone()[0]
            session['pid'] = user_id
            pair_check = db.execute(sqlalchemy.text('select id from pairs where mod_id=:user_id'), user_id=user_id).fetchone()
            if pair_check is not None and pair_check[0] is not None:
                session[JOB_VAR] = JOB_MOD_VAL
            else:
                session[JOB_VAR] = JOB_OBS_VAL
            job = session[JOB_VAR]
            
            if job == JOB_MOD_VAL:
                output = db.execute(sqlalchemy.text('select id, create_time from pairs where mod_id=:uid'), uid=pid).fetchone()
                pair_id = output[0]
                create_time = output[1]
            else:
                output = db.execute(sqlalchemy.text('select id, create_time from pairs where obs_id=:uid'), uid=pid).fetchone()
                pair_id = output[0]
                create_time = output[1]
            return render_template('wait.html', pair_id=pair_id, room_name='pair-{}-{}'.format(pair_id, create_time), turk_id=uid, role=job)

    # Determining worker condition
    cond = request.args.get(CONDITION_VAR)
    if was_observer is not None: # Condition was assigned as URL param (testing)
        cond = CONDITION_EXP_VAL
        db.execute(sqlalchemy.text('update mod_forms set curr_index=0, responses=\'\' where turk_id=:uid'), uid=uid)
    elif cond is None: # Condition is assigned randomly (experiment)
        cond = CONDITION_CON_VAL if random.random() < 0.5 else CONDITION_EXP_VAL
    session[CONDITION_VAR] = cond

    if worker_exists is False:
        polArg = request.args.get('pol')
        if polArg is None:
            affiliation = 'Unspecified'
        else:
            affiliation = urllib.parse.unquote(polArg)
        print('{}: insert turk_id={}, condition={}, and affiliation={} into participants'.format(WAIT_PAGE, uid, cond, affiliation))
        result = db.execute(sqlalchemy.text('insert into participants(turk_id, condition, political_affiliation, was_waiting) VALUES(:uid, :cond, :affiliation, :waiting) '), uid=uid, cond=cond, affiliation=affiliation, waiting=True)
        pid = db.execute(sqlalchemy.text('select user_id from participants where turk_id=:uid'), uid=uid).fetchone()[0]
        db.execute(sqlalchemy.text('insert into mod_forms(turk_id, curr_index, responses) VALUES(:uid, 0, \'\')'), uid=uid)
    session['pid'] = pid

    # Determining worker job
    if was_observer is not None:
        job = JOB_MOD_VAL
    else:
        if cond == CONDITION_CON_VAL: # Worker is in control condition they've been an observer
            job = JOB_MOD_VAL
        else:
            unpaired_pairs = db.execute(sqlalchemy.text('select id from pairs where mod_id IS NULL and obs_id!=:uid'), uid=pid).fetchall()
            if unpaired_pairs is not None and len(unpaired_pairs) == 1 and unpaired_pairs[0] is not None and unpaired_pairs[0][0] == 1:
                job = JOB_MOD_VAL

        # unpaired_obs = db.execute(sqlalchemy.text('select obs_id from pairs where mod_id IS NULL and obs_id!=:uid'), uid=uid).fetchone()
        # if unpaired_obs is not None:
        #     for obs_id in unpaired_obs: # Checking if all unpaired observers are already finished with task and can't be paired
        #         edge_case = db.execute(sqlalchemy.text('select edge_case from participants where turk_id=:obs_id'), obs_id=obs_id[0]).fetchone()
        #         if edge_case is not None and edge_case[0] != 'Unpaired observer':
        #             job = JOB_MOD_VAL
        #             break
            else:
                currently_working_pairs = [x[0] for x in db.execute(sqlalchemy.text('select id from pairs where obs_id IS NOT NULL and mod_id IS NOT NULL and (obs_submitted IS NULL or mod_submitted IS NULL) and disconnect_occurred is NULL and restarted IS NULL')).fetchall()]
                unpaired_moderators = [x[0] for x in db.execute(sqlalchemy.text('select id from pairs where mod_id IS NOT NULL and obs_id IS NULL and restarted IS NULL')).fetchall()]

                if len(currently_working_pairs) == 0 and len(unpaired_moderators) == 0: # All other workers are finished/disconnected
                    job = JOB_MOD_VAL
                else:
                    job = JOB_OBS_VAL

    session[JOB_VAR] = job


    # Worker pairing logic
    if cond == CONDITION_EXP_VAL: # Experimental condition
        # check = db.execute(sqlalchemy.text('select turk_id from participants where turk_id=:uid'), uid=uid).fetchone() # Check if worker is already in the system
        if worker_exists is False: # Worker was not previously in system
            if job == JOB_MOD_VAL: # Moderator role
                paired = check_edge_case(pid)
            elif job == JOB_OBS_VAL: # Observer role
                mod_id = db.execute(sqlalchemy.text('select mod_id from pairs where obs_id IS NULL and restarted IS NULL')).fetchone()
                if mod_id is None: # Creating new pair
                    print('{}: insert obs_id={} and create_time={} into pairs'.format(WAIT_PAGE, pid, time.time()))
                    db.execute(sqlalchemy.text('insert into pairs(obs_id, create_time) VALUES(:uid, :time)'), uid=pid, time=time.time())
                else: # Pairing with existing moderator
                    print('{}: set obs_id={} where mod_id={} in pairs'.format(WAIT_PAGE, pid, mod_id[0]))
                    db.execute(sqlalchemy.text('update pairs set obs_id=:uid where mod_id=:mod_id'), uid=pid, mod_id=mod_id[0])
        elif was_observer is not None: # Worker was previously an observer and is now a moderator
            paired = check_edge_case(pid)

    if cond == CONDITION_EXP_VAL:
        if job == JOB_MOD_VAL:
            output = db.execute(sqlalchemy.text('select id, create_time from pairs where mod_id=:uid'), uid=pid).fetchone()
            pair_id = output[0]
            create_time = output[1]
        else:
            output = db.execute(sqlalchemy.text('select id, create_time from pairs where obs_id=:uid'), uid=pid).fetchone()
            pair_id = output[0]
            create_time = output[1]

        # Set initial ping time on page load
        if job == JOB_MOD_VAL:
            db.execute(sqlalchemy.text('update pairs set last_mod_time=:time where id=:pair_id'), time=time.time(), pair_id=pair_id)
        else:
            db.execute(sqlalchemy.text('update pairs set last_obs_time=:time where id=:pair_id'), time=time.time(), pair_id=pair_id)

        return render_template('wait.html', pair_id=pair_id, room_name='pair-{}-{}'.format(pair_id, create_time), turk_id=uid, role=job)
    else:
        return redirect(url_for(WORK_PAGE))

# You or your partner was previously disconnected, ending task
@app.route('/disconnect')
def do_disconnect():
    turk_id = request.args.get('turkId')
    db.execute(sqlalchemy.text('update participants set work_complete=TRUE where turk_id=:turk_id'), turk_id=turk_id)
    
    disconnector = request.args.get('dc')
    return render_template('disconnect.html', dc=disconnector)

# Waiting worker polls server to see if they've been flagged to start working
@app.route("/" + POLL_WORK_READY_PAGE, methods=['POST'])
def poll_work_ready():
    json = request.json

    pair_id = json['pair_id']
    role = json['role']
    work_ready = db.execute(sqlalchemy.text('select work_ready from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]
    
    # Updating last wait page ping times
    time_now = time.time()
    if role == 'obs':
        db.execute(sqlalchemy.text('update pairs set last_obs_wait=:time_now where id=:pair_id'), time_now=time_now, pair_id=pair_id)
    else:
        db.execute(sqlalchemy.text('update pairs set last_mod_wait=:time_now where id=:pair_id'), time_now=time_now, pair_id=pair_id)
    
    if work_ready is not None:
        return jsonify(status='success')
    else:
        return jsonify(status='failure')

# Update state of moderator form in control condition in case of reconnect
@app.route('/control_form_update', methods=['POST'])
def control_form_update():
    json = request.json
    
    turk_id = json['turk_id']
    curr_index = json['curr_index']
    responses = json['responses']
    
    db.execute(sqlalchemy.text('update mod_forms set curr_index=:curr_index, responses=:responses where turk_id=:turk_id'), curr_index=curr_index, responses=responses, turk_id=turk_id)
    return jsonify(status='success')

# Indicate that user has pressed "I'm ready" button
@app.route('/set_worker_ready', methods=['POST'])
def set_worker_ready():
    json = request.json

    pair_id = json['pair_id']
    worker = json['worker']

    if worker == 'mod':
        db.execute(sqlalchemy.text('update pairs set mod_ready=TRUE where id=:pair_id'), pair_id=pair_id)
    else:
        db.execute(sqlalchemy.text('update pairs set obs_ready=TRUE where id=:pair_id'), pair_id=pair_id)

    return jsonify(status='success')

# Check if both workers have selected the "I'm ready" button
@app.route('/check_workers_ready', methods=['POST'])
def check_workers_ready():
    pair_id = request.json['pair_id']

    mod_ready = db.execute(sqlalchemy.text('select mod_ready from pairs where id=:pair_id'), pair_id=pair_id).fetchone()
    obs_ready = db.execute(sqlalchemy.text('select obs_ready from pairs where id=:pair_id'), pair_id=pair_id).fetchone()

    if mod_ready[0] is None or obs_ready[0] is None: # Not ready
        return jsonify(status='not ready')
    else: # Both ready
        return jsonify(status='ready')

# Marks image as revealed on moderator's client, allows observer to respond for this image
@app.route("/reveal_image", methods=['POST'])
def reveal_image():
    json = request.json
    
    pair_id = json['pair_id']
    img_index = json['img_index']
    
    # Check if image has already been revealed
    result = db.execute(sqlalchemy.text('select * from images_revealed where pair_id=:pair_id and img_index=:index'), pair_id=pair_id, index=img_index).fetchone()
    
    # Mark as revealed to observer
    if result is None:
        db.execute(sqlalchemy.text('insert into images_revealed(pair_id, img_index) VALUES(:pair_id, :index)'), pair_id=pair_id, index=img_index)
    
    # Update current moderator form state to current image (for both users in pair)
    pair_members = db.execute(sqlalchemy.text('select mod_id, obs_id from pairs where id=:pair_id'), pair_id=pair_id).fetchone()
    mod_turk = db.execute(sqlalchemy.text('select turk_id from participants where user_id=:mod_id'), mod_id=pair_members[0]).fetchone()[0]
    obs_turk = db.execute(sqlalchemy.text('select turk_id from participants where user_id=:obs_id'), obs_id=pair_members[1]).fetchone()[0]
    db.execute(sqlalchemy.text('update mod_forms set curr_index=:curr_index where turk_id=:mod_turk'), curr_index=img_index, mod_turk=mod_turk)
    db.execute(sqlalchemy.text('update mod_forms set curr_index=:curr_index where turk_id=:obs_turk'), curr_index=img_index, obs_turk=obs_turk)
    
    return jsonify(status='success')

# Update decision on revealed image as moderator makes selections
@app.route('/update_temp_decision', methods=['POST'])
def update_temp_decision():
    json = request.json

    pair_id = json['pair_id']
    img_index = json['img_index']
    decision = json['decision']
    choices = json['choices']
    
    db.execute(sqlalchemy.text('update images_revealed set temp_decision=:temp_decision where pair_id=:pair_id and img_index=:img_index'), temp_decision=decision, pair_id=pair_id, img_index=img_index)

    # Update moderator form state for both users in pair
    responses = ''
    for i in range(0, len(choices)):
        if choices[i] == 'Yes' or choices[i] == 'No':
            responses += choices[i]
        else:
            break
        
        if i != len(choices) - 1 and (choices[i + 1] == 'Yes' or choices[i + 1] == 'No'):
            responses += ','
    
    pair_members = db.execute(sqlalchemy.text('select mod_id, obs_id from pairs where id=:pair_id'), pair_id=pair_id).fetchone()
    mod_turk = db.execute(sqlalchemy.text('select turk_id from participants where user_id=:mod_id'), mod_id=pair_members[0]).fetchone()[0]
    obs_turk = db.execute(sqlalchemy.text('select turk_id from participants where user_id=:obs_id'), obs_id=pair_members[1]).fetchone()[0]
    db.execute(sqlalchemy.text('update mod_forms set responses=:responses where turk_id=:mod_turk'), responses=responses, mod_turk=mod_turk)
    db.execute(sqlalchemy.text('update mod_forms set responses=:responses where turk_id=:obs_turk'), responses=responses, obs_turk=obs_turk)
    
    return jsonify(status='success')

# Check which images moderator has revealed
@app.route('/check_revealed', methods=['POST'])
def check_revealed():
    json = request.json

    pair_id = json['pair_id']

    # Check which images have been revealed for this pair
    results = db.execute(sqlalchemy.text('select * from images_revealed where pair_id=:pair_id'), pair_id=pair_id).fetchall()

    # Parse results
    indices = []
    for result in results:
        indices.append(result[2])

    # Get moderator response to each image
    mod_responses = []
    for img_index in indices:
        response = db.execute(sqlalchemy.text('select temp_decision from images_revealed where pair_id=:pair_id and img_index=:img_index'), pair_id=pair_id, img_index=img_index).fetchone()
        if response[0] is None:
            mod_responses.append('')
        else:
            mod_responses.append(response[0])

    return jsonify(status='success', indices=indices, mod_responses=mod_responses)

# Submits moderator decisions to database
@app.route("/" + SUBMIT_MODS_PAGE, methods=['POST'])
def accept_moderations():
    json = request.json

    pair_id = json['pair_id']
    img_ids = json['img_ids']
    decisions = json['decisions']

    for i in range(NUM_IMAGES):
        if pair_id == 0: # Worker was in control group
            print('{}: insert decision={} and img_id={} into moderations'.format(SUBMIT_MODS_PAGE, decisions[i], img_ids[i]))
            db.execute(sqlalchemy.text('insert into moderations(decision, img_id) VALUES(:decision, :img_id)'),decision=decisions[i], img_id=img_ids[i])
        else: # Worker was in experimental group
            print('{}: insert decision={}, img_id={}, and pair_id={} into moderations'.format(SUBMIT_MODS_PAGE, decisions[i], img_ids[i], pair_id))
            db.execute(sqlalchemy.text('insert into moderations(decision, img_id, pair_id) VALUES(:decision, :img_id, :pair_id)'),decision=decisions[i], img_id=img_ids[i], pair_id=pair_id)

    print('{}: set mod_submitted=True where id={} in pairs'.format(SUBMIT_MODS_PAGE, pair_id))
    db.execute(sqlalchemy.text('update pairs set mod_submitted=:sub where id=:pair_id'), sub=True, pair_id=pair_id)
    return jsonify(status='success')

# Submits observer responses to database
@app.route("/" + SUBMIT_OBS_PAGE, methods=['POST'])
def accept_observations():

    json = request.json
    pair_id = json['pair_id']
    img_ids = json['img_ids']
    agreements = json['agreements']

    for i in range(NUM_IMAGES):
        db.execute(sqlalchemy.text('insert into observations(pair_id, img_id, agreement_text) VALUES(:pair_id, :img_id, :agreement)'), pair_id=pair_id, img_id=img_ids[i], agreement=agreements[i])

    db.execute(sqlalchemy.text('update pairs set obs_submitted=TRUE where id=:pair_id'), pair_id=pair_id)
    session[WAS_OBSERVER_VAR] = 'true'
    return jsonify(status='success')

# Ping server to acknowledge that you're still connected, check if partner is still connected
@app.route('/ping', methods=['POST'])
def do_ping():
    pair_id = request.json['pair_id']
    role = request.json['role']
    check_dc = request.json['check_dc']

    curr_time = time.time()
    if role == 'mod':
        db.execute(sqlalchemy.text('update pairs set last_mod_time=:time where id=:pair_id'), time=curr_time, pair_id=pair_id)
        last_time = db.execute(sqlalchemy.text('select last_obs_time from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]
        partner_finished = db.execute(sqlalchemy.text('select obs_submitted from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0] is not None
    else:
        db.execute(sqlalchemy.text('update pairs set last_obs_time=:time where id=:pair_id'), time=curr_time, pair_id=pair_id)
        last_time = db.execute(sqlalchemy.text('select last_mod_time from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]
        partner_finished = db.execute(sqlalchemy.text('select mod_submitted from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0] is not None

    if check_dc == 'yes':
        if last_time is None:
            return jsonify(partner_status='disconnected')
        elif curr_time - float(last_time) >= TIMEOUT and not partner_finished:
            return jsonify(partner_status='disconnected')
        else:
            return jsonify(partner_status='connected')
    else:
        return jsonify(partner_status='connected')

# Mark disconnected partner and invalid pair
@app.route('/mark_disconnection')
def mark_disconnection():
    pair_id = request.args.get('pair_id')
    role = request.args.get('role')
    turk_id = request.args.get('turkId')

    db.execute(sqlalchemy.text('update pairs set disconnect_occurred=:occurred where id=:pair_id'), occurred=True, pair_id=pair_id)

    if role == 'mod':
        dc_id = db.execute(sqlalchemy.text('select obs_id from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]
    else:
        dc_id = db.execute(sqlalchemy.text('select mod_id from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]

    db.execute(sqlalchemy.text('update participants set disconnected=:occurred where user_id=:dc_id'), occurred=True, dc_id=dc_id)

    return redirect('/disconnect?turkId=%s&dc=other' % turk_id)

# Gets user color for moderator based on political affiliation, observer by random selection
def get_user_color(randomize):
    politicizing = True # For debug
    if politicizing:
        turk_id = session[TURK_ID_VAR]
        if randomize:
            prev_rand = db.execute(sqlalchemy.text('select randomized_affiliation from participants where turk_id=:turk_id'), turk_id=turk_id).fetchone()[0]
            if prev_rand is not None:
                if prev_rand == 'Conservative':
                    return RED
                elif prev_rand == 'Liberal':
                    return BLUE
                else:
                    return GRAY

            val = random.uniform(0, 1)

            if val < 0.333:
                rand_aff = 'Conservative'
                rand_color = RED
            elif val < 0.667:
                rand_aff = 'Liberal'
                rand_color = BLUE
            else:
                rand_aff = 'Other'
                rand_color = GRAY

            db.execute(sqlalchemy.text('update participants set randomized_affiliation=:rand_aff where turk_id=:turk_id'), rand_aff=rand_aff, turk_id=turk_id)
            return rand_color;
        else:
            affiliation = db.execute(sqlalchemy.text('select political_affiliation from participants where turk_id=:turk_id'), turk_id=turk_id).fetchone()[0]

            if affiliation == 'Conservative':
                return RED
            elif affiliation == 'Liberal':
                return BLUE
            else:
                return GRAY
    else:
        return '#{:06x}'.format(random.randint(0, 256**3))

# Work page where observing/moderation occurs
@app.route("/" + WORK_PAGE)
def work():
    turkId = session[TURK_ID_VAR]
    job = session[JOB_VAR]
    condition = session[CONDITION_VAR]
    session[WAS_WAITING_VAR] = None
    was_waiting = db.execute(sqlalchemy.text('update participants set was_waiting=:was_waiting where turk_id=:uid'), was_waiting=None, uid=turkId)
    pid = session.get('pid')
    user_color = get_user_color(job == JOB_OBS_VAL)

    # If experiment is complete and worker is an unpaired moderator, move them to the control condition
    # If experiment is complete and worker is an unpaired observer, move them to the Done page
    complete = db.execute(sqlalchemy.text('select complete from exp_complete')).fetchone()
    experiment_complete = complete is not None and complete[0] is not None

    unpaired_mod = db.execute(sqlalchemy.text('select id from pairs where mod_id=:turk_id and obs_id is NULL'), turk_id=pid).fetchone()
    if experiment_complete and unpaired_mod is not None:
        db.execute(sqlalchemy.text('update participants set edge_case=:case where turk_id=:turk_id'), case='Last', turk_id=turkId)

    # Getting current pair and corresponding observer and moderator IDs
    if condition == CONDITION_EXP_VAL:
        if job == JOB_MOD_VAL:
            obs, mod = db.execute(sqlalchemy.text('select obs_id, mod_id from pairs where mod_id=:turk_id'), turk_id=pid).fetchone()
            page = 'moderation'
        else:
            holder = db.execute(sqlalchemy.text('select obs_id, mod_id from pairs where obs_id=:turk_id'), turk_id=pid).fetchone()
            if holder is not None:
                obs, mod = holder
            else:
                mod = None

            if mod is None: # Observer cannot work without paired moderator (edge case)
                print('{}: insert turk_id={}, response=No into consent'.format(WORK_PAGE, turkId))
                db.execute(sqlalchemy.text('insert into consent(turk_id, response) VALUES(:turk_id, :no)'), turk_id=turkId, no='No')
                print('{}: set edge_case=Unpaired Observer where turk_id={} in participants'.format(WORK_PAGE, turkId))
                db.execute(sqlalchemy.text('update participants set edge_case=:obs where turk_id=:turk_id'), obs='Unpaired observer', turk_id=turkId)
                
                # Mark work as complete
                user_id = db.execute(sqlalchemy.text('select user_id from participants where turk_id=:turk_id'), turk_id=turkId).fetchone()[0]
                pair_id = db.execute(sqlalchemy.text('update pairs set obs_submitted=:submitted where obs_id=:user_id'), submitted=True, user_id=user_id)
                
                return render_template('done.html', turk_id=turkId, task_finished=False)

            page = 'observation'
        if obs is None:
            output = db.execute(sqlalchemy.text('select id, create_time from pairs where obs_id IS NULL and mod_id=:mod'), mod=mod).fetchone()
            pair_id = output[0]
            create_time = output[1]
        else:
            output = db.execute(sqlalchemy.text('select id, create_time from pairs where obs_id=:obs and mod_id=:mod'), obs=obs, mod=mod).fetchone()
            pair_id = output[0]
            create_time = output[1]
    else:
        pair_id = 0
        page = 'moderation'

    # Constructing room name as concatenation of moderator and observer IDs (only in experimental condition)
    room_name = 'pair-{}-{}'.format(pair_id, create_time) if condition == CONDITION_EXP_VAL else ''

    # Getting first pair that isn't an unpaired observer
    all_pairs = db.execute(sqlalchemy.text('select * from pairs order by id ASC'))
    first_pair_with_mod = 0
    for p in all_pairs:
        mod_id = p[2]
        if mod_id is not None:
            first_pair_with_mod = p[0]
            break

    # Checking for edge cases
    edge_check = db.execute(sqlalchemy.text('select edge_case from participants where turk_id=:turk_id'), turk_id=turkId).fetchone()
    if pair_id == first_pair_with_mod and job == JOB_MOD_VAL and unpaired_mod is None:
        edge_case = 'First'
        print('{}: set edge_case=First where turk_id={} in participants'.format(WORK_PAGE, turkId))
        db.execute(sqlalchemy.text('update participants set edge_case=:edge where turk_id=:turk_id'), edge=edge_case, turk_id=turkId)
    elif edge_check is not None and edge_check[0] == 'Last':
        edge_case = 'Last'
        condition = CONDITION_CON_VAL # Simulating control condition if this is the last worker (no observer)
    else:
        edge_case = None

	# Getting all image URLs in database
    all_imgs = db.execute(sqlalchemy.text('select path,affiliation from images')).fetchall()

    chosen_imgs = db.execute(sqlalchemy.text('select img_id from chosen_imgs where pair_id=:pair_id'), pair_id=pair_id).fetchall() # Check if worker's pair has already been assigned images
    if chosen_imgs is None or len(chosen_imgs) == 0: # Images have not already been assigned to paired partner
        if condition == CONDITION_CON_VAL: # Images in control condition
            control_imgs = db.execute(sqlalchemy.text('select img_id from control_imgs where turk_id=:turk_id'), turk_id=turkId).fetchall()
            if control_imgs is None or len(control_imgs) == 0:
                subset = get_array_subset(all_imgs, NUM_IMAGES, [])
                for s in subset:
                    img_id = db.execute(sqlalchemy.text('select img_id from images where path=:path'), path=s[0]).fetchone()[0]
                    db.execute(sqlalchemy.text('insert into control_imgs(img_id, turk_id) VALUES(:img_id, :turk_id)'), img_id=img_id, turk_id=turkId)
            else:
                subset = []
                for control_img in control_imgs:
                    img_path = db.execute(sqlalchemy.text('select path,affiliation from images where img_id=:img_id'), img_id=control_img[0]).fetchone()
                    subset.append(img_path);
        else:
            curr_mod = db.execute(sqlalchemy.text('select mod_id from pairs where id=:pair_id'), pair_id=pair_id).fetchone()
            cannot_contain = []
            if curr_mod is not None:
                # Checking if worker was previously paired (as an observer)
                last_pair = db.execute(sqlalchemy.text('select id from pairs where obs_id=:curr_mod'), curr_mod=curr_mod[0]).fetchone()
                if last_pair is not None:
                    # Finding images that were previously seen by this worker so they don't moderate the same ones
                    cannot_contain_ids = db.execute(sqlalchemy.text('select img_id from moderations where pair_id=:last'), last=last_pair[0])
                    for id in cannot_contain_ids:
                        path = db.execute(sqlalchemy.text('select path,affiliation from images where img_id=:id'), id=id[0]).fetchone()
                        cannot_contain.append(path)
            subset = get_array_subset(all_imgs, NUM_IMAGES, cannot_contain) # Randomly selecting images for the task
            if pair_id != 0:
                # Setting images as chosen so paired partner sees the same ones
                for s in subset:
                    id = db.execute(sqlalchemy.text('select img_id from images where path=:path'), path=s[0]).fetchone()[0]
                    print('{}: insert img_id={}, pair_id={} into chosen_imgs'.format(WORK_PAGE, id, pair_id))
                    db.execute(sqlalchemy.text('insert into chosen_imgs(img_id, pair_id) VALUES(:id, :pair)'), id=id, pair=pair_id)
    else:
        subset = []
        for img_id in chosen_imgs: # Getting images that have already been assigned to partner
            path = db.execute(sqlalchemy.text('select path from images where img_id=:img_id'), img_id=img_id[0]).fetchone()
            subset.append(path)

    # Extracting image URLs from chosen subset and their corresponding IDs
    img_subset = [str(s[0]) for s in subset]
    print('Image paths on user load: %s' % img_subset)
    extraction = [db.execute(sqlalchemy.text('select img_id, poster, text from images where path=:img_subset'), img_subset=img_subset[i]).fetchone() for i in range(len(img_subset))]
    img_ids, usernames, posts = zip(*extraction)

    # Set last time right before work begins
    curr_time = time.time()
    if page == 'moderation':
        db.execute(sqlalchemy.text('update pairs set last_mod_time=:time where id=:pair_id'), time=curr_time, pair_id=pair_id)
        last_time = db.execute(sqlalchemy.text('select last_obs_time from pairs where id=:pair_id'), pair_id=pair_id).fetchone()
    else:
        db.execute(sqlalchemy.text('update pairs set last_obs_time=:time where id=:pair_id'), time=curr_time, pair_id=pair_id)
        last_time = db.execute(sqlalchemy.text('select last_mod_time from pairs where id=:pair_id'), pair_id=pair_id).fetchone()

    if condition == CONDITION_CON_VAL:
        is_ready = True
    else:
        # Check if pair has pressed "I'm ready"
        mod_ready = db.execute(sqlalchemy.text('select mod_ready from pairs where id=:pair_id'), pair_id=pair_id).fetchone()
        obs_ready = db.execute(sqlalchemy.text('select obs_ready from pairs where id=:pair_id'), pair_id=pair_id).fetchone()

        if mod_ready[0] is None or obs_ready[0] is None: # Not ready
            is_ready = False
        else: # Both ready
            is_ready = True
    
    # Fetching current state of moderator form (all users in both conditions)
    mod_form_state = db.execute(sqlalchemy.text('select curr_index, responses from mod_forms where turk_id=:turk_id'), turk_id=turkId).fetchone()
    curr_index = mod_form_state[0]
    responses = mod_form_state[1]
    
    return render_template('work.html', page=page, condition=condition, room_name=room_name, imgs=img_subset, img_ids=list(img_ids), img_count=NUM_IMAGES, pair_id=pair_id, edge_case=edge_case, user_color=user_color, usernames=list(usernames), posts=list(posts), is_ready=is_ready, turk_id=turkId, curr_index=curr_index, responses=responses)
