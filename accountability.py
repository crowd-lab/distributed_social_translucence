from flask import Flask, session, redirect, url_for, request, render_template, jsonify
import random
import base64
import sqlite3
import sqlalchemy
from flask import g
import hashlib
import time
import os

# App setup
app = Flask(__name__)
app.secret_key = b'\xbfEdVSb\xc6\x91Q\x02\x1c\xa7cN\xba$'
app.dev = False

# Default directories and values
DATABASE = './database.db'
IMAGE_DIR = 'static/images/'
NUM_IMAGES = 3
experiment_complete = False
TIMEOUT = 20

# Page URLs
WAIT_PAGE = 'wait'
DASHBOARD_PAGE = 'dashboard'
SUBMIT_MODS_PAGE = 'submit_mods'
SUBMIT_OBS_PAGE = 'submit_obs'
CHECK_MOD_SUBMITTED_PAGE = 'check_mod_submitted'
CHECK_OBS_SUBMITTED_PAGE = 'check_obs_submitted'
WORK_PAGE = 'work'
DONE_PAGE = 'done'
NARRATIVE_PAGE = 'narrative'
CONSENT_PAGE = 'consent'
EXPERIMENT_COMPLETE_PAGE = 'experiment_complete'
POLL_WORK_READY_PAGE = 'poll_work_ready'
MARK_WORK_READY_PAGE = 'mark_work_ready'

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

# App initialization
with app.app_context():
    db = get_db()

    # Load database schema
    db.exectute(sqlalchemy.text('create table if not exists images (img_id serial primary key, path text unique, text text, poster text, affiliation text);')
    db.execute(sqlalchemy.text('create table if not exists participants (user_id serial primary key, turk_id text unique, condition text, edge_case text, disconnected boolean);')
    db.execute(sqlalchemy.text('create table if not exists pairs (id serial primary key, obs_id integer unique references participants(user_id), mod_id integer unique references participants(user_id), obs_submitted boolean, mod_submitted boolean, work_ready boolean, mod_ready boolean, obs_ready boolean, last_mod_time real, last_obs_time real, disconnect_occurred boolean, create_time numeric);')
    db.execute(sqlalchemy.text('create table if not exists observations(id serial primary key, pair_id integer references pairs(id), obs_text text, img_id integer, agreement_text text);')
    db.execute(sqlalchemy.text('create table if not exists moderations(id serial primary key, decision text, img_id integer references images(img_id), pair_id integer references pairs(id));')
    db.execute(sqlalchemy.text('create table if not exists chosen_imgs(id serial primary key, img_id integer, pair_id integer);')
    db.execute(sqlalchemy.text('create table if not exists images_revealed(id serial primary key, pair_id integer, img_index integer);')
    db.execute(sqlalchemy.text('create table if not exists consent(id serial primary key, turk_id text unique, response text);')

    # with open('db.schema', mode='r') as f:
    #     results = db.execute(sqlalchemy.text(f.read()))
        
        # db.cursor().executescript(f.read())
    # db.commit()

    # Load images (if none are loaded)
    out = db.execute('select count(*) from images')
    count = out.fetchall()[0][0]
    if count == 0:
        load_images_to_db()

# Gets subset of all images to be displayed
def get_array_subset(array, num_vals, cannot_contain):
    assert len(array) - len(cannot_contain) >= num_vals
    subset = []
    while len(subset) < num_vals: # Add num_vals images
        i = random.randint(0, len(array) - 1)
        val = array[i]

        # Don't add image if it was already seen previously in observer role
        if val not in subset and val not in cannot_contain:
            subset.append(val)
    return subset

# Dashboard page
@app.route('/' + DASHBOARD_PAGE)
def dashboard():
    # Get workers in control group and pairs in experimental group
    participants=db.execute(sqlalchemy.text('select * from participants')).fetchall()
    control = [p for p in participants if p[2] == CONDITION_CON_VAL]
    pairs = db.execute(sqlalchemy.text('select * from pairs')).fetchall()

    done_class = 'class="worker-done"' # Class that marks worker/pair as finished on dashboard

    # Construct control table elements
    control_html = ''
    for c in control:
        worker_id = c[1]
        worker_done = db.execute(sqlalchemy.text('select response from consent where turk_id=:worker_id'), worker_id=worker_id).fetchone() is not None
        done_text = done_class if worker_done else ''
        control_html += '<tr><th {} scope="row">{}</th><td {}>{}</td></tr>'.format(done_text, c[0], done_text, worker_id)

    # Construct experimental table elements
    experiment_html = ''
    for p in pairs:
        pair_id = p[0]
        mod_id = db.execute(sqlalchemy.text('select mod_id from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]
        if mod_id is not None:
            pair_obs_id = db.execute(sqlalchemy.text('select obs_id from pairs where id=:pair_id'), pair_id=pair_id).fetchone()

            # get the turk_ids for moderator and paired observer
            mod_turk = db.execute(sqlalchemy.text('select turk_id from participants where user_id=:mod_id'), mod_id=mod_id).fetchone()[0]
            print('mod_turk: {}'.format(mod_turk))
            pair_obs_turk = db.execute(sqlalchemy.text('select turk_id from participants where user_id=:pair_obs_id'), pair_obs_id=pair_obs_id[0]).fetchone()[0]

            worker_done = db.execute(sqlalchemy.text('select response from consent where turk_id=:mod_id'), mod_id=mod_turk).fetchone() is not None
            pair_obs_skipped = False if pair_obs_turk is None else db.execute(sqlalchemy.text('select response from consent where turk_id=:obs_id'), obs_id=pair_obs_turk[0]).fetchone() is not None
            done_text = done_class if worker_done or pair_obs_skipped else ''
            work_ready = db.execute(sqlalchemy.text('select work_ready from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]
            work_ready_btn = '<button ' + ('disabled' if work_ready is not None else '') + ' onclick="markPairWorking(\'' + str(pair_id) + '\', this)">Start Work</button>'
            unpaired_mod = mod_turk is not None and pair_obs_turk is None
            unpaired_obs = mod_turk is None and pair_obs_turk is not None
            if (unpaired_mod or unpaired_obs) and not experiment_complete:
                work_ready_btn = ''

            mod_id_text = '' if p[2] is None else mod_turk
            obs_id_text = '' if p[1] is None else pair_obs_turk

            disconnect_style = '' if p[10] is None else 'style="opacity: 0.25; pointer-events: none;"'

            experiment_html += '<tr {}><th {} scope="row">{}{}</th><td {}>{}</td><td {}>{}</td></tr>'.format(disconnect_style, done_text, pair_id, work_ready_btn, done_text, mod_id_text, done_text, obs_id_text)

    return render_template('dashboard.html', control_html=control_html, experiment_html=experiment_html, experiment_complete=experiment_complete)

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
    global experiment_complete
    experiment_complete = True

    unpaired_mods = db.execute(sqlalchemy.text('select mod_id from pairs where obs_id is null')).fetchall()
    for mod_id in unpaired_mods:
        print('{}: setting edge_case=Last in participants where user_id={}'.format(EXPERIMENT_COMPLETE_PAGE, mod_id[0]))
        db.execute(sqlalchemy.text('update participants set edge_case=:last where user_id=:mod_id'), last='Last', mod_id=mod_id[0])

    return jsonify(status='success')

# Narrative page
@app.route("/" + NARRATIVE_PAGE)
def narrative():
    session.clear()

    turkId = request.args.get(TURK_ID_VAR)
    assignmentId = request.args.get(ASSIGNMENT_ID_VAR)

    session[TURK_ID_VAR] = turkId
    session[ASSIGNMENT_ID_VAR] = assignmentId
    session[WAS_WAITING_VAR] = None

    return render_template('narrative.html', turkId=turkId)

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

    return render_template('done.html', turk_id=turk_id, task_finished=True)

# returns True if the person got paired, or False if a new pair was created
def check_edge_case(user_id):
    obs_ids = db.execute(sqlalchemy.text('select obs_id from pairs where mod_id IS NULL')).fetchall()
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

# Wait page
@app.route("/" + WAIT_PAGE)
def wait():
    uid = session[TURK_ID_VAR]
    pid = 0
    if 'user_color' in session.keys():
        user_color = session['user_color']
    else: 
        user_color = session['user_color'] = get_user_color()

    # Checking if user is trying to rejoin after a disconnect
    disconnected = db.execute(sqlalchemy.text('select disconnected from participants where turk_id=:turk_id'), turk_id=uid).fetchone()
    print(disconnected)
    if disconnected is not None and disconnected[0] is not None:
        return redirect('/disconnect?dc=you')

    # Experiment is finished and user doesn't need to wait
    if experiment_complete:
        return render_template('done.html', turk_id=uid, task_finished=False)

    # Checking if worker was already on the wait page (i.e. a refresh occurred)
    if session[WAS_WAITING_VAR] is not None:
        job = session[JOB_VAR]
        user_id = db.execute(sqlalchemy.text('select user_id from participants where turk_id=:uid'), uid=uid).fetchone()[0]
        if job == JOB_MOD_VAL:
            output = db.execute(sqlalchemy.text('select id, create_time from pairs where mod_id=:uid'), uid=user_id).fetchone()
            pair_id = output[0]
            create_time = output[1]
        else:
            output = db.execute(sqlalchemy.text('select id, create_time from pairs where obs_id=:uid'), uid=user_id).fetchone()
            pair_id = output[0]
            create_time = output[1]
        return render_template('wait.html', pair_id=pair_id, room_name='pair-{}-{}'.format(pair_id, create_time), user_color=user_color)
    else:
        session[WAS_WAITING_VAR] = 'Yes'

    was_observer = session.get(WAS_OBSERVER_VAR)
    session[WAS_OBSERVER_VAR] = None

    # Exiting early if worker has already been added to system
    pid = db.execute(sqlalchemy.text('select user_id from participants where turk_id=:uid'), uid=uid).fetchone()
    worker_exists = pid is not None
    if worker_exists:
        pid = pid[0]

    if worker_exists and not was_observer:
        return render_template('wait.html')

    # Determining worker condition
    cond = request.args.get(CONDITION_VAR)
    if was_observer is not None: # Condition was assigned as URL param (testing)
        cond = CONDITION_EXP_VAL
    elif cond is None: # Condition is assigned randomly (experiment)
        cond = CONDITION_CON_VAL if random.random() < 0.5 else CONDITION_EXP_VAL
    session[CONDITION_VAR] = cond

    if worker_exists is False:
        print('{}: insert turk_id={} and condition={} into participants'.format(WAIT_PAGE, uid, cond))
        result = db.execute(sqlalchemy.text('insert into participants(turk_id, condition) VALUES(:uid, :cond) '), uid=uid, cond=cond)
        pid = db.execute(sqlalchemy.text('select user_id from participants where turk_id=:uid'), uid=uid).fetchone()[0]
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
                currently_working_pairs = [x[0] for x in db.execute(sqlalchemy.text('select id from pairs where obs_id IS NOT NULL and mod_id IS NOT NULL and (obs_submitted IS NULL or mod_submitted IS NULL) and disconnect_occurred is NULL')).fetchall()]
                unpaired_moderators = [x[0] for x in db.execute(sqlalchemy.text('select id from pairs where mod_id IS NOT NULL and obs_id IS NULL')).fetchall()]

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
                mod_id = db.execute(sqlalchemy.text('select mod_id from pairs where obs_id IS NULL')).fetchone()
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

        return render_template('wait.html', pair_id=pair_id, room_name='pair-{}-{}'.format(pair_id, create_time), user_color=user_color)
    else:
        return redirect(url_for(WORK_PAGE))

# You or your partner was previously disconnected, ending task
@app.route('/disconnect')
def do_disconnect():
    disconnector = request.args.get('dc')
    return render_template('disconnect.html', dc=disconnector)

# Waiting worker polls server to see if they've been flagged to start working
@app.route("/" + POLL_WORK_READY_PAGE, methods=['POST'])
def poll_work_ready():
    json = request.json

    pair_id = json['pair_id']
    work_ready = db.execute(sqlalchemy.text('select work_ready from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]

    if work_ready is not None:
        return jsonify(status='success')
    else:
        return jsonify(status='failure')

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

    if mod_ready is None or obs_ready is None: # Not ready
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

    return jsonify(status='success', indices=indices)

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
    comments = json['comments']

    for i in range(NUM_IMAGES):
        db.execute(sqlalchemy.text('insert into observations(pair_id, img_id, obs_text, agreement_text) VALUES(:pair_id, :img_id, :comment, :agreement)'), pair_id=pair_id, img_id=img_ids[i], comment=comments[i], agreement=agreements[i])

    db.execute(sqlalchemy.text('update pairs set obs_submitted=TRUE where id=:pair_id'), pair_id=pair_id)
    session[WAS_OBSERVER_VAR] = 'true'
    return jsonify(status='success')

# Ping server to acknowledge that you're still connected, check if partner is still connected
@app.route('/ping', methods=['POST'])
def do_ping():
    pair_id = request.json['pair_id']
    role = request.json['role']

    curr_time = time.time()
    if role == 'mod':
        db.execute(sqlalchemy.text('update pairs set last_mod_time=:time where id=:pair_id'), time=curr_time, pair_id=pair_id)
        last_time = db.execute(sqlalchemy.text('select last_obs_time from pairs where id=:pair_id'), pair_id=pair_id).fetchone()
        partner_finished = db.execute(sqlalchemy.text('select obs_submitted from pairs where id=:pair_id'), pair_id=pair_id).fetchone() is not None
    else:        
        db.execute(sqlalchemy.text('update pairs set last_obs_time=:time where id=:pair_id'), time=curr_time, pair_id=pair_id)
        last_time = db.execute(sqlalchemy.text('select last_mod_time from pairs where id=:pair_id'), pair_id=pair_id).fetchone()
        partner_finished = db.execute(sqlalchemy.text('select mod_submitted from pairs where id=:pair_id'), pair_id=pair_id).fetchone() is not None
    
    if last_time[0] is None:
        last_time = curr_time + TIMEOUT - 1
    else:
        last_time = last_time[0]

    if curr_time - last_time >= TIMEOUT and not partner_finished:
        return jsonify(partner_status='disconnected')
    else:
        return jsonify(partner_status='connected')

# Mark disconnected partner and invalid pair
@app.route('/mark_disconnection')
def mark_disconnection():
    pair_id = request.args.get('pair_id')
    role = request.args.get('role')

    db.execute(sqlalchemy.text('update pairs set disconnect_occurred=TRUE where id=:pair_id'), pair_id=pair_id)

    if role == 'mod':
        dc_id = db.execute(sqlalchemy.text('select obs_id from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]
    else:
        dc_id = db.execute(sqlalchemy.text('select mod_id from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]

    db.execute(sqlalchemy.text('update participants set disconnected=TRUE where turk_id=:dc_id'), dc_id=dc_id)

    return redirect('/disconnect?dc=other')

def get_user_color():
    politicizing = True
    if politicizing:
        return '#ff0000' if random.getrandbits(1) else '#0000ff'
    else:
        return '#{:06x}'.format(random.randint(0, 256**3))

# Work page where observing/moderation occurs
@app.route("/" + WORK_PAGE)
def work():
    user_color = session['user_color']
    turkId = session.get(TURK_ID_VAR)
    job = session[JOB_VAR]
    condition = session[CONDITION_VAR]
    session[WAS_WAITING_VAR] = None
    pid = session.get('pid')

    # Getting current pair and corresponding observer and moderator IDs
    if condition == CONDITION_EXP_VAL:
        if job == JOB_MOD_VAL:
            obs, mod = db.execute(sqlalchemy.text('select obs_id, mod_id from pairs where mod_id=:turk_id'), turk_id=pid).fetchone()
            page = 'moderation'
        else:
            holder = db.execute(sqlalchemy.text('select obs_id, mod_id from pairs where obs_id=:turk_id'), turk_id=pid).fetchone()
            if holder is not None:
                obs, mod = holder

            if mod is None: # Observer cannot work without paired moderator (edge case)
                print('{}: insert turk_id={}, response=No into consent'.format(WORK_PAGE, turkId))
                db.execute(sqlalchemy.text('insert into consent(turk_id, response) VALUES(:turk_id, :no)'), turk_id=turkId, no='No')
                print('{}: set edge_case=Unpaired Observer where turk_id={} in participants'.format(WORK_PAGE, turkId))
                db.execute(sqlalchemy.text('update participants set edge_case=:obs where turk_id=:turk_id'), obs='Unpaired observer', turk_id=turkId)
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
    if pair_id == first_pair_with_mod and job == JOB_MOD_VAL:
        edge_case = 'First'
        print('{}: set edge_case=First where turk_id={} in participants'.format(WORK_PAGE, turkId))
        db.execute(sqlalchemy.text('update participants set edge_case=:edge where turk_id=:turk_id'), edge=edge_case, turk_id=turkId)
    elif edge_check is not None and edge_check[0] == 'Last':
        edge_case = 'Last'
        condition = CONDITION_CON_VAL # Simulating control condition if this is the last worker (no observer)
    else:
        edge_case = None

	# Getting all image URLs in database
    all_imgs = db.execute(sqlalchemy.text('select path from images')).fetchall()

    chosen_imgs = db.execute(sqlalchemy.text('select img_id from chosen_imgs where pair_id=:pair_id'), pair_id=pair_id).fetchall() # Check if worker's pair has already been assigned images
    if chosen_imgs is None or len(chosen_imgs) == 0: # Images have not already been assigned to paired partner
        curr_mod = db.execute(sqlalchemy.text('select mod_id from pairs where id=:pair_id'), pair_id=pair_id).fetchone()
        cannot_contain = []
        if curr_mod is not None:
            # Checking if worker was previously paired (as an observer)
            last_pair = db.execute(sqlalchemy.text('select id from pairs where obs_id=:curr_mod'), curr_mod=curr_mod[0]).fetchone()
            if last_pair is not None:
                # Finding images that were previously seen by this worker so they don't moderate the same ones
                cannot_contain_ids = db.execute(sqlalchemy.text('select img_id from moderations where pair_id=:last'), last=last_pair[0])
                for id in cannot_contain_ids:
                    path = db.execute(sqlalchemy.text('select path from images where img_id=:id'), id=id[0]).fetchone()
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

    return render_template('work.html', page=page, condition=condition, room_name=room_name, imgs=img_subset, img_ids=list(img_ids), img_count=NUM_IMAGES, pair_id=pair_id, edge_case=edge_case, user_color=user_color, usernames=list(usernames), posts=list(posts))
