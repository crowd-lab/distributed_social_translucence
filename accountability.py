from flask import Flask, session, redirect, url_for, escape, request, render_template, jsonify
import random
import base64
import sqlite3
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

# Get parameters in URL
TURK_ID_VAR = 'workerId'
ASSIGNMENT_ID_VAR = 'assignmentId'
CONSENT_VAR = 'consent'
JOB_VAR = 'j'
CONDITION_VAR = 'c'
WAS_OBSERVER_VAR = 'was_observer'
IS_LAST_VAR = 'isLast'

# Possible values for Get parameters
JOB_MOD_VAL = 'mod'
JOB_OBS_VAL = 'obs'
CONDITION_CON_VAL = 'con'
CONDITION_EXP_VAL = 'exp'

# Close database
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Get database reference
def get_db():
    db = getattr(g, '_database', None)
    if db is None: # Launch database if it hasn't been
        db = g._database = sqlite3.connect(DATABASE)
    return db

# Query database
def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    get_db().commit()
    cur.close()
    return (rv[0] if rv else None) if one else rv

# Load image paths from images folder to database
def load_images_to_db():
    files = os.listdir(IMAGE_DIR)
    for f in files:
        db.execute('insert into images(img_path) VALUES(?)', [IMAGE_DIR + f])
    db.commit()

# App initialization
with app.app_context():
    db = get_db()

    # Load database schema
    with app.open_resource('db.schema', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()

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
    participants=query_db('select * from participants', one=False)
    control = [p for p in participants if p[2] == CONDITION_CON_VAL]
    pairs = query_db('select * from pairs', one=False)

    done_class = 'class="worker-done"' # Class that marks worker/pair as finished on dashboard

    # Construct control table elements
    control_html = ''
    for c in control:
        worker_id = c[1]
        worker_done = query_db('select response from consent where turk_id=?', [worker_id], one=True) is not None
        done_text = done_class if worker_done else ''
        control_html += '<tr><th {} scope="row">{}</th><td {}>{}</td></tr>'.format(done_text, c[0], done_text, worker_id)

    # Construct experimental table elements
    experiment_html = ''
    for p in pairs:
        pair_id = p[0]
        mod_id = query_db('select mod_id from pairs where id=?', [pair_id], one=True)
        if mod_id is not None:
            worker_done = query_db('select response from consent where turk_id=?', [mod_id[0]], one=True) is not None
            done_text = done_class if worker_done else ''
            experiment_html += '<tr><th {} scope="row">{}</th><td {}>{}</td><td {}>{}</td></tr>'.format(done_text, pair_id, done_text, p[2], done_text, p[1])

    return render_template('dashboard.html', control_html=control_html, experiment_html=experiment_html)

# Narrative page
@app.route("/" + NARRATIVE_PAGE)
def narrative():
    turkId = request.args.get(TURK_ID_VAR)
    assignmentId = request.args.get(ASSIGNMENT_ID_VAR)

    session[TURK_ID_VAR] = turkId
    session[ASSIGNMENT_ID_VAR] = assignmentId

    return render_template('narrative.html', turkId=turkId)

# Consent page
@app.route("/" + CONSENT_PAGE)
def consent():
    turkId = session[TURK_ID_VAR]
    query_db('insert into consent(turk_id, response) VALUES(?, ?)', [turkId, 'No'])
    return render_template('consent.html')

# Done page
@app.route("/" + DONE_PAGE)
def done():
    turk_id = session.get(TURK_ID_VAR)
    consent = request.args.get(CONSENT_VAR)

    if consent == 'Yes':
        query_db('update consent set response=? where turk_id=?', [consent, turk_id])

    return render_template('done.html', turk_id=turk_id)

# Wait page
@app.route("/" + WAIT_PAGE)
def wait():
    was_observer = session.get(WAS_OBSERVER_VAR)
    session[WAS_OBSERVER_VAR] = None
    uid = session[TURK_ID_VAR]

    cond = request.args.get(CONDITION_VAR)
    if was_observer is not None: # Condition was assigned as URL param (testing)
        cond = CONDITION_EXP_VAL
    elif cond is None: # Condition is assigned randomly (experiment)
        cond = CONDITION_CON_VAL if random.random() < 0.5 else CONDITION_EXP_VAL
    session[CONDITION_VAR] = cond

    if was_observer is not None: # Worker was previously an observer
        job = JOB_MOD_VAL
    else:
        if cond == CONDITION_CON_VAL: # Worker is in control condition
            job = JOB_MOD_VAL
        else:
            unpaired_obs = query_db('select id from pairs where mod_id IS NULL', one=True)
            if unpaired_obs is None: # No one is waiting for a pair
                job = JOB_OBS_VAL
            else: # An observer is waiting for a pair
                job = JOB_MOD_VAL
    session[JOB_VAR] = job

    # Worker pairing logic
    if cond == CONDITION_EXP_VAL: # Experimental condition
        check = query_db('select turk_id from participants where turk_id=?', [uid], one=True) # Check if worker is already in the system
        if check is None: # Worker was not previously in system
            query_db('insert into participants(turk_id, condition) VALUES(?, ?)', [uid, cond], one=True)
            pid = query_db('select user_id from participants where turk_id=?', [uid], one=True)
            if job == JOB_MOD_VAL: # Moderator role
                obs_id = query_db('select obs_id from pairs where mod_id IS NULL', one=True)
                if obs_id is None: # Creating new pair
                    query_db('insert into pairs(mod_id) VALUES(?)', [uid])
                else: # Pairing with existing observer
                    query_db('update pairs set mod_id=? where obs_id=?', [uid, obs_id[0]])
            elif job == JOB_OBS_VAL: # Observer role
                mod_id = query_db('select mod_id from pairs where obs_id IS NULL', one=True)
                if mod_id is None: # Creating new pair
                    query_db('insert into pairs(obs_id) VALUES(?)', [uid])
                else: # Pairing with existing moderator
                    query_db('update pairs set obs_id=? where mod_id=?', [uid, mod_id[0]])
        elif was_observer is not None: # Worker was previously an observer and is now a moderator
            pair_id = query_db('select id from pairs where obs_id=?', [None], one=True)
            if pair_id is None: # Create new pair if there's no unpaired observer
                query_db('insert into pairs(mod_id) VALUES(?)', [uid])
            else: # Pair this worker with waiting observer
                query_db('update pairs set mod_id=? where pair_id=?', [uid, pair_id])
    else: # Control condition
        check = query_db('select turk_id from participants where turk_id=?', [uid], one=True)
        if check is None: # Add worker to control condition if they aren't already in the system
            query_db('insert into participants(turk_id, condition) VALUES(?, ?)', [uid, cond], one=True)

    return render_template('wait.html')

# Submits moderator decisions to database
@app.route("/" + SUBMIT_MODS_PAGE, methods=['POST'])
def accept_moderations():
    json = request.json

    pair_id = json['pair_id']
    img_ids = json['img_ids']
    decisions = json['decisions']

    for i in range(NUM_IMAGES):
        if pair_id == 0: # Worker was in control group
            query = 'insert into moderations(decision, img_id) VALUES(?, ?)'
            query_db(query, [decisions[i], img_ids[i]], one=True)
        else: # Worker was in experimental group
            query = 'insert into moderations(decision, img_id, pair_id) VALUES(?, ?, ?)'
            query_db(query, [decisions[i], img_ids[i], pair_id], one=True)

    query_db('update pairs set mod_submitted=? where id=?', [True, pair_id])
    return jsonify(status='success')

# Observer polls if moderator has submitted their responses
@app.route("/" + CHECK_MOD_SUBMITTED_PAGE, methods=['POST'])
def check_mod_submitted():
    json = request.json
    pair_id = json['pair_id']

    query = 'select mod_submitted from pairs where id=?'
    val = query_db(query, [pair_id])

    if val is not None and val[0] is not None and val[0][0] is not None and val[0][0]:
        return jsonify(status='success', submitted='true')
    else:
        return jsonify(status='success', submitted='false')

# Moderator polls if observer has submitted their responses
@app.route("/" + CHECK_OBS_SUBMITTED_PAGE, methods=['POST'])
def check_obs_submitted():
    json = request.json
    pair_id = json['pair_id']

    query = 'select obs_submitted from pairs where id=?'
    val = query_db(query, [pair_id])

    if val is not None and val[0] is not None and val[0][0] is not None and val[0][0]:
        return jsonify(status='success', submitted='true')
    else:
        return jsonify(status='success', submitted='false')

# Submits observer responses to database
@app.route("/" + SUBMIT_OBS_PAGE, methods=['POST'])
def accept_observations():
    json = request.json

    query = 'insert into observations(pair_id, obs_text) VALUES(?, ?)'
    query_db(query, [json['pair_id'], json['obs_text']], one=True)

    query_db('update pairs set obs_submitted=? where id=?', [True, json['pair_id']])

    session[WAS_OBSERVER_VAR] = 'true'
    return jsonify(status='success')

# Work page where observing/moderation occurs
@app.route("/" + WORK_PAGE)
def work():
    turkId = session.get(TURK_ID_VAR)
    job = session[JOB_VAR]
    condition = session[CONDITION_VAR]

    # Simulating control condition if this is the last worker (no observer)
    isLast = request.args.get(IS_LAST_VAR)
    if isLast is not None:
        condition = CONDITION_CON_VAL

    # Getting current pair and corresponding observer and moderator IDs
    if condition == CONDITION_EXP_VAL:
        if job == JOB_MOD_VAL:
            obs, mod = query_db('select obs_id, mod_id from pairs where mod_id=?', [turkId], one=True)
            page = 'moderation'
        else:
            obs, mod = query_db('select obs_id, mod_id from pairs where obs_id=?', [turkId], one=True)
            page = 'observation'
        pair_id = query_db('select id from pairs where obs_id=? and mod_id=?', [obs, mod], one=True)[0]
    else:
        pair_id = 0
        page = 'moderation'

    # Constructing room name as concatenation of moderator and observer IDs (only in experimental condition)
    room_name = '{}|{}'.format(obs, mod) if condition == CONDITION_EXP_VAL else ''

    # Checking for edge cases
    if pair_id == 1 and job == JOB_MOD_VAL:
        edge_case = 'First'
    elif isLast is not None:
        condition = CONDITION_CON_VAL # Simulating control condition if this is the last worker (no observer)
        edge_case = 'Last'
    else:
        edge_case = None
    query_db('update participants set edge_case=? where turk_id=?', [edge_case, turkId])

	# Getting all image URLs in database
    all_imgs = query_db('select img_path from images')

    chosen_imgs = query_db('select img_id from chosen_imgs where pair_id=?', [pair_id]) # Check if worker's pair has already been assigned images
    if chosen_imgs is None or len(chosen_imgs) == 0: # Images have not already been assigned to paired partner
        curr_mod = query_db('select mod_id from pairs where id=?', [pair_id], one=True)
        cannot_contain = []
        if curr_mod is not None:
            # Checking if worker was previously paired (as an observer)
            last_pair = query_db('select id from pairs where obs_id=?', [curr_mod[0]], one=True)
            if last_pair is not None:
                # Finding images that were previously seen by this worker so they don't moderate the same ones
                cannot_contain_ids = query_db('select img_id from moderations where pair_id=?', [last_pair[0]])
                for id in cannot_contain_ids:
                    path = query_db('select img_path from images where img_id=?', [id[0]], one=True)
                    cannot_contain.append(path)
        subset = get_array_subset(all_imgs, NUM_IMAGES, cannot_contain) # Randomly selecting images for the task
        if pair_id != 0:
            # Setting images as chosen so paired partner sees the same ones
            for s in subset:
                id = query_db('select img_id from images where img_path=?', [s[0]], one=True)[0]
                query_db('insert into chosen_imgs(img_id, pair_id) VALUES(?, ?)', [id, pair_id])
    else:
        subset = []
        for img_id in chosen_imgs: # Getting images that have already been assigned to partner
            path = query_db('select img_path from images where img_id=?', [img_id[0]], one=True)
            subset.append(path)

    # Extracting image URLs from chosen subset and their corresponding IDs
    img_subset = [str(s[0]) for s in subset]
    img_ids = [query_db('select img_id from images where img_path=?', [img_subset[i]], one=True)[0] for i in range(len(img_subset))]

    return render_template('work.html', page=page, condition=condition, room_name=room_name, imgs=img_subset, img_ids=img_ids, img_count=NUM_IMAGES, pair_id=pair_id, edge_case=edge_case)
