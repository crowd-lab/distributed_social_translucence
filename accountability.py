from flask import Flask, session, redirect, url_for, escape, request, render_template, jsonify
import random
import base64
import sqlite3
from flask import g
import hashlib
import time
import os

app = Flask(__name__)

app.secret_key = b'\xbfEdVSb\xc6\x91Q\x02\x1c\xa7cN\xba$'
app.dev = False

DATABASE = './database.db'
IMAGE_DIR = "static/images/"
NUM_IMAGES = 4

# Renaming database file with timestamp if it already exists
#if os.path.exists(DATABASE):
#    os.rename(DATABASE, DATABASE + '_' + str(time.time()))

ERROR_PAGE = 'error'
CLEAR_PAGE = 'clear'
WAIT_PAGE = 'wait'
DASHBOARD_PAGE = 'dashboard'
SUBMIT_MODS_PAGE = 'submit_mods'
SUBMIT_OBS_PAGE = 'submit_obs'
CHECK_MOD_SUBMITTED_PAGE = 'check_mod_submitted'
CHECK_OBS_SUBMITTED_PAGE = 'check_obs_submitted'
ROOT_PAGE = ''
ROOT_NAME = 'router'
WORK_PAGE = 'work'
OBS_TO_MOD_PAGE = "obs_to_mod"
DONE_PAGE = 'done'
NARRATIVE_PAGE = 'narrative'
CONSENT_PAGE = 'consent'

TURK_ID_VAR = 'workerId'
JOB_VAR = 'j'
STEP_VAR = 's'
CONDITION_VAR = 'c'

JOB_MOD_VAL = 'mod'
JOB_OBS_VAL = 'obs'
STEP_WAIT_1_VAL = 'wa1'
STEP_WAIT_2_VAL = 'wa2'
STEP_WORK_1_VAL = 'wo1'
STEP_WORK_2_VAL = 'wo2'
CONDITION_CON_VAL = 'con'
CONDITION_EXP_VAL = 'exp'

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db


def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    get_db().commit()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def load_images_to_db():
    files = os.listdir(IMAGE_DIR)
    for f in files:
        db.execute('insert into images(img_path) VALUES(?)', [IMAGE_DIR + f])
    db.commit()

with app.app_context():
    db = get_db()
    with app.open_resource('db.schema', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()
    out = db.execute('select count(*) from images')
    count = out.fetchall()[0][0]
    if count == 0:
        load_images_to_db()

def get_condition():
    options = [CONDITION_CON_VAL, CONDITION_EXP_VAL]
    if CONDITION_VAR not in session:
        if request.args.get(CONDITION_VAR) in options:
            session[CONDITION_VAR] = request.args.get(CONDITION_VAR)
        else:
            session[CONDITION_VAR] = options[random.getrandbits(1)]

    return session[CONDITION_VAR]

def get_job(step, condition):
    if step == STEP_WAIT_1_VAL and condition == CONDITION_EXP_VAL:
        return JOB_OBS_VAL

    return JOB_MOD_VAL

def supposed_to_be_here(from_func, step, condition):
    print(condition)
    if app.dev:
        return True

    if from_func == ROOT_NAME and step != STEP_WAIT_1_VAL and step != STEP_WAIT_2_VAL:
        print('\tcoming from ' + ROOT_NAME + ' and wrong step')
        return False

    if from_func == WORK_PAGE:
        if step is not STEP_WORK_1_VAL and condition == CONDITION_CON_VAL:
            print('\tcoming from ' + WORK_PAGE + ' and control condition and observation job')
            return False
        if condition == CONDITION_EXP_VAL and step != STEP_WORK_1_VAL and step != STEP_WORK_2_VAL:
            print('\tcoming from ' + WORK_PAGE + ' and experimental condition and observation job but large step')
            return False

    return True

def get_page_values(job, step, condition):
    color = 'white'
    page = 'moderation'
    reason = ''
    print('page values: {}, {}, {}'.format(job, step, condition))
    if condition == CONDITION_CON_VAL:
        reason = 'you are in the control condition'
        print('page values control')
    elif condition == CONDITION_EXP_VAL and step == STEP_WORK_1_VAL:
        page = 'observation'
        reason = 'you are in the experimental condition and this is the first time you have visited'
        print('page values experimental1')
    elif condition == CONDITION_EXP_VAL and step == STEP_WORK_2_VAL:
        reason = 'you are in the experimental condition and this is the second time you have visited'
        print('page values experimental2')
    else:
        color = 'red'
        page = 'error'
        reason = 'you are not supposed to be here anymore, job: ' + job + ', step: ' + step + ', condition: ' + condition
        print('page values error')

    return color, page, reason

def get_array_subset(array, num_vals, cannot_contain):
    assert len(array) - len(cannot_contain) >= num_vals
    subset = []
    while len(subset) < num_vals:
        i = random.randint(0, len(array) - 1)
        val = array[i]
        if val not in subset and val not in cannot_contain:
            subset.append(val)
    return subset

@app.route("/" + NARRATIVE_PAGE)
def narrative():
    turkId = request.args.get(TURK_ID_VAR)
    session[TURK_ID_VAR] = turkId
    return render_template('narrative.html', turkId=turkId)

@app.route("/" + CONSENT_PAGE)
def consent():
    turkId = session[TURK_ID_VAR]

    query_db('insert into consent(turk_id, response) VALUES(?, ?)', [turkId, 'No'])

    return render_template('consent.html')

@app.route("/" + DONE_PAGE)
def done():
    turk_id = session.get(TURK_ID_VAR)
    consent = request.args.get('consent')

    if consent == 'Yes':
        query_db('update consent set response=? where turk_id=?', ['Yes', turk_id])

    #hash_in = turk_id + str(time.time())
    #hash = str(hashlib.sha256(hash_in.encode()).hexdigest())

    #query_db('insert into hashes(turk_id, hash) VALUES(?, ?)', [turk_id, hash])

    return render_template('done.html', turk_id=turk_id)

@app.route("/" + ERROR_PAGE)
def error():
    turkId = request.args.get(TURK_ID_VAR)
    step, condition = query_db('select b.state, a.condition from participants as a, participants_state as b where b.turk_id=? and a.turk_id=b.turk_id', [turkId], one=True)
    print('ERROR PAGE - step: {}, condition: {}'.format(step, condition))
    color, page, reason = get_page_values('', '', '')
    return render_template('base.html', color=color, page=page, reason=reason, img_ids=[], img_count=NUM_IMAGES) # put img list?

@app.route("/" + CLEAR_PAGE)
def clear():
    # clear the session if I tell you to
    if app.dev:
        session.clear()
        return redirect(url_for(WAIT_PAGE, turkId='jts_test'))
    else:
        return redirect(url_for(ERROR_PAGE, turkId='jts_test'))

@app.route("/" + WAIT_PAGE)
def wait():
    was_observer = session.get('was_observer')
    session['was_observer'] = None

    if app.dev:
        session.clear()

    if TURK_ID_VAR not in session.keys():
        session[TURK_ID_VAR] = request.args.get(TURK_ID_VAR)
    uid = session[TURK_ID_VAR]

    if was_observer is not None:
        cond = CONDITION_EXP_VAL
    else:
        cond = CONDITION_CON_VAL if random.random() < 0.5 else CONDITION_EXP_VAL

    # Assigning job based on whether an unpaired individual exists
    if was_observer is not None:
        job = JOB_MOD_VAL
    else:
        if cond == CONDITION_CON_VAL:
            job = JOB_MOD_VAL
        else:
            unpaired_obs = query_db('select id from pairs where mod_id IS NULL', one=True)
            if unpaired_obs is None:
                job = JOB_OBS_VAL
            else:
                job = JOB_MOD_VAL

    session[JOB_VAR] = job
    session[CONDITION_VAR] = cond

    # TODO: remove
    print('User ' + str(uid) + ' is a ' + str(job) + ' in the ' + str(cond) + ' condition, observer: ' + str(was_observer))

    if cond == CONDITION_EXP_VAL:
        check = query_db('select turk_id from participants where turk_id=?', [uid], one=True)
        if check is None:
            query_db('insert into participants(turk_id, condition) VALUES(?, ?)', [uid, session[CONDITION_VAR]], one=True)
            query_db('insert into participants_state(turk_id, state) VALUES(?, ?)', [uid, STEP_WAIT_1_VAL], one=True)
            pid = query_db('select user_id from participants where turk_id=?', [uid], one=True)
            if job == JOB_MOD_VAL:
                obs_id = query_db('select obs_id from pairs where mod_id IS NULL', one=True)
                if obs_id is None:
                    query_db('insert into pairs(mod_id) VALUES(?)', [uid])
                else:
                    query_db('update pairs set mod_id=? where obs_id=?', [uid, obs_id[0]])
            elif job == JOB_OBS_VAL:
                mod_id = query_db('select mod_id from pairs where obs_id IS NULL', one=True)
                print("Obs pair ID is " + str(mod_id))
                if mod_id is None:
                    query_db('insert into pairs(obs_id) VALUES(?)', [uid])
                else:
                    query_db('update pairs set obs_id=? where mod_id=?', [uid, mod_id[0]])
        elif was_observer is not None:
            pair_id = query_db('select id from pairs where obs_id=?', [None], one=True)
            if pair_id is None:
                query_db('insert into pairs(mod_id) VALUES(?)', [uid])
            else:
                query_db('update pairs set mod_id=? where pair_id=?', [uid, pair_id])
        else:
            query_db('update participants_state set state=? where turk_id=?', [STEP_WAIT_2_VAL, uid], one=True)
    else:
        check = query_db('select turk_id from participants where turk_id=?', [uid], one=True)
        if check is None:
            query_db('insert into participants(turk_id, condition) VALUES(?, ?)', [uid, session[CONDITION_VAR]], one=True)
            query_db('insert into participants_state(turk_id, state) VALUES(?, ?)', [uid, STEP_WAIT_1_VAL], one=True)
        else:
            query_db('update participants_state set state=? where turk_id=?', [STEP_WAIT_2_VAL, uid], one=True)

    return render_template('base.html', color='gray', page='waiting', reason='', img_ids=[], img_count=NUM_IMAGES)

@app.route('/' + DASHBOARD_PAGE)
def dashboard():
    participants=query_db('select * from participants', one=False)
    control = [p for p in participants if p[2]==CONDITION_CON_VAL]
    pairs = query_db('select * from pairs', one=False)

    control_html = ''.join(['<tr><th scope="row">{}</th><td>{}</td></tr>'.format(c[0], c[1]) for c in control])
    experiment_html = ''.join(['<tr><th scope="row">{}</th><td>{}</td><td>{}</td></tr>'.format(c[0], c[2], c[1]) for c in pairs])

    return render_template('dashboard.html', control_html=control_html, experiment_html=experiment_html)

@app.route("/" + OBS_TO_MOD_PAGE)
def obs_to_mod():
    session['was_observer'] = 'True'

    return redirect(url_for(WAIT_PAGE))

@app.route("/" + SUBMIT_MODS_PAGE, methods=['POST'])
def accept_moderations():
    json = request.json

    pair_id = json['pair_id']
    img_ids = json['img_ids']
    decisions = json['decisions']
    for i in range(NUM_IMAGES):
        if pair_id == 0:
            query = 'insert into moderations(decision, img_id) VALUES(?, ?)'
            query_db(query, [decisions[i], img_ids[i]], one=True)
        else:
            query = 'insert into moderations(decision, img_id, pair_id) VALUES(?, ?, ?)'
            query_db(query, [decisions[i], img_ids[i], pair_id], one=True)

    query_db('update pairs set mod_submitted=? where id=?', [True, pair_id])

    return jsonify(status='success');

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

@app.route("/" + SUBMIT_OBS_PAGE, methods=['POST'])
def accept_observations():
    json = request.json

    query = 'insert into observations(pair_id, obs_text) VALUES(?, ?)'
    query_db(query, [json['pair_id'], json['obs_text']], one=True)

    query_db('update pairs set obs_submitted=? where id=?', [True, json['pair_id']])

    session['was_observer'] = 'true'

    return jsonify(status='success');

@app.route("/" + ROOT_PAGE)
def index():
    turkId = session[TURK_ID_VAR]
    session['isLast'] = request.args.get('isLast')
    print('The turk id is: ' + str(turkId))
    step, condition = query_db('select b.state, a.condition from participants as a, participants_state as b where b.turk_id=? and a.turk_id=b.turk_id', [turkId], one=True)
    if app.dev:
        #session[STEP_VAR] = request.args.get(STEP_VAR)
        session[CONDITION_VAR] = condition

    print('ROUTER PAGE - step: {}, condition: {}'.format(step, condition))

    print(supposed_to_be_here(ROOT_NAME, step, condition))
    if not supposed_to_be_here(ROOT_NAME, step, condition):
        print('ERROR /' + ROOT_PAGE)
        return redirect(url_for(ERROR_PAGE, turkId=turkId))

    job = session[JOB_VAR]

    # need logic here for figuring out which room people get routed to

    print('\trouting to {}'.format(job))
    #session[JOB_VAR] = base64.urlsafe_b64encode(job.encode()).decode('ascii') if not app.dev else job
    return redirect(url_for(WORK_PAGE))

@app.route("/" + WORK_PAGE)
def work():
    job = session.get(JOB_VAR)
    message = 'WORK PAGE - '
    turkId = session.get(TURK_ID_VAR)
    step, condition = query_db('select b.state, a.condition from participants as a, participants_state as b where b.turk_id=? and a.turk_id=b.turk_id', [turkId], one=True) if not app.dev else session[STEP_VAR], session[CONDITION_VAR]

    if step == STEP_WAIT_1_VAL and job == JOB_OBS_VAL:
        query_db('update participants_state set state=? where turk_id=?', [STEP_WORK_1_VAL, turkId])
    elif step == STEP_WAIT_1_VAL and job == JOB_MOD_VAL and condition == CONDITION_CON_VAL:
        query_db('update participants_state set state=? where turk_id=?', [STEP_WORK_1_VAL, turkId])
    elif step == STEP_WAIT_2_VAL and job == JOB_MOD_VAL:
        query_db('update participants_state set state=? where turk_id=?', [STEP_WORK_2_VAL, turkId])
    step, condition = query_db('select b.state, a.condition from participants as a, participants_state as b where b.turk_id=? and a.turk_id=b.turk_id', [turkId], one=True)

    isLast = session['isLast']
    if isLast is not None:
        condition = CONDITION_CON_VAL

    # You shouldn't be able to do anything else
    #if not supposed_to_be_here(WORK_PAGE, step, condition):
        #print('ERROR /' + WORK_PAGE)
        #return redirect(url_for(ERROR_PAGE, turkId=turkId))

    if condition == CONDITION_EXP_VAL:
        if job == JOB_MOD_VAL:
            obs, mod = query_db('select obs_id, mod_id from pairs where mod_id=?', [turkId], one=True)
            pair_id = query_db('select id from pairs where obs_id=? and mod_id=?', [obs, mod], one=True)[0]
            print(message + 'moderation task')
        elif job == JOB_OBS_VAL:
            obs, mod = query_db('select obs_id, mod_id from pairs where obs_id=?', [turkId], one=True)
            pair_id = query_db('select id from pairs where obs_id=? and mod_id=?', [obs, mod], one=True)[0]
            print(message + 'observation task')
        else:
            print('ERROR /' + WORK_PAGE + ' 2')
            return redirect(url_for(ERROR_PAGE, turkId=turkId))
        print('obs|mod: {}|{}'.format(obs, mod))
    else:
        pair_id = 0

    # Manually setting work step
    if job == JOB_OBS_VAL:
        step = STEP_WORK_1_VAL
    else:
        step = STEP_WORK_2_VAL

    color, page, reason = get_page_values(job, step, condition)
    room_name = '{}|{}'.format(obs, mod) if condition == CONDITION_EXP_VAL else ''
    print(room_name)

	# Getting all image URLs
    all_imgs = query_db('select img_path from images')

    # Getting list of images this user has already observed
    # Saving, retrieving, and/or generating random subset for this pair
    chosen_imgs = query_db('select img_id from chosen_imgs where pair_id=?', [pair_id])
    if chosen_imgs is None or len(chosen_imgs) == 0:
        curr_mod = query_db('select mod_id from pairs where id=?', [pair_id], one=True)
        cannot_contain = []
        if curr_mod is not None:
            last_pair = query_db('select id from pairs where obs_id=?', [curr_mod[0]], one=True)
            if last_pair is not None:
                cannot_contain_ids = query_db('select img_id from moderations where pair_id=?', [last_pair[0]])
                for id in cannot_contain_ids:
                    path = query_db('select img_path from images where img_id=?', [id[0]], one=True)
                    cannot_contain.append(path)
        subset = get_array_subset(all_imgs, NUM_IMAGES, cannot_contain)
        if pair_id != 0:
            for s in subset:
                id = query_db('select img_id from images where img_path=?', [s[0]], one=True)[0]
                query_db('insert into chosen_imgs(img_id, pair_id) VALUES(?, ?)', [id, pair_id])
    else:
        subset = []
        for img_id in chosen_imgs:
            path = query_db('select img_path from images where img_id=?', [img_id[0]], one=True)
            subset.append(path)

    # img_subset = [s[0].encode("ascii") for s in subset]
    img_subset = [str(s[0]) for s in subset]
    print('Images in db: %s' % img_subset)
    img_ids = query_db('select img_id from images where img_path in (%s)' % ('"' + '", "'.join(img_subset) + '"'), one=True)[0]
    print('Image IDs: %s' % img_ids)

    # check if first or last (first is pair_id=1, last is marked by URL param isLast), mark and update edge_case accordingly (0 or 1)
    # Disable autoStart in base.html if first, move (value only) to control condition if last

    edge_check_pair = query_db('select id from pairs where mod_id=?', [turkId], one=True)
    if edge_check_pair is not None and edge_check_pair[0] == 1:
        first = True
    else:
        first = False

    if isLast is not None:
        last = True
    else:
        last = False

    if last:
        condition = CONDITION_CON_VAL

    if first or last:
        edge_case = 1
    else:
        edge_case = 0
    query_db('update participants set edge_case=? where turk_id=?', [edge_case, turkId])

    return render_template('base.html', color=color, page=page, condition=condition, reason=reason, room_name=room_name, imgs=img_subset, img_ids=img_ids, img_count=NUM_IMAGES, pair_id=pair_id, first=first)
