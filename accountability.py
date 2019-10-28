from flask import Flask, session, redirect, url_for, request, render_template, jsonify
import random
import json
import base64
import sqlite3
import sqlalchemy
from flask import g
import hashlib
import time
import os
import urllib.parse
import names

# App setup
app = Flask(__name__)
app.secret_key = b'\xbfEdVSb\xc6\x91Q\x02\x1c\xa7cN\xba$'
app.dev = False

# Default directories and values
DATABASE = './database.db'
IMAGE_DIR = 'static/images/'
NUM_IMAGES = 10 # TODO: 10
NON_POLITICAL_IMG_PERCENTAGE = 0.1
TIMEOUT = 120
WORK_PAGE_ACTIVITY_TIMER = 8
WAIT_PAGE_ACTIVITY_TIMER = 8
DEV = True # TODO: False
SHOW_AFFILIATION = True
PILOT_NOW = True

# Page URLs
WAIT_PAGE = 'wait'
DASHBOARD_PAGE = 'dashboard'
SUBMIT_MODS_PAGE = 'submit_mods'
SUBMIT_OBS_PAGE = 'submit_obs'
WORK_PAGE = 'new_work'
DONE_PAGE = 'done'
NARRATIVE_PAGE = 'narrative'
CONSENT_PAGE = 'consent'
EXPERIMENT_COMPLETE_PAGE = 'experiment_complete'
NEW_TRIAL_PAGE = 'new_trial'
POLL_WORK_READY_PAGE = 'poll_work_ready'
MARK_WORK_READY_PAGE = 'mark_work_ready'
POLITIC_PAGE = 'political_affiliation'

# Get parameters in URL
TURK_ID_VAR = 'workerId'
ASSIGNMENT_ID_VAR = 'assignmentId'
CONSENT_VAR = 'consent'
POSITION_VAR = 'position'
POSITION_RIGHT_WORKER = 'r'
POSITION_LEFT_WORKER = 'l'
CONDITION_VAR = 'c'
WAS_OBSERVER_VAR = 'was_observer'
IS_LAST_VAR = 'isLast'
WAS_WAITING_VAR = 'was_waiting'

# Possible values for Get parameters
JOB_MOD_VAL = 'mod'
JOB_OBS_VAL = 'obs'
CONTROL = 'control'
MOVEMENT = 'movement'
ANSWERS = 'answers'
CHAT = 'chat'
CONDITIONS = range(1,4)
# CONDITIONS = range(1,5) # for when we activate chat

def get_random_condition(new_pair, pair_id): 
    if not new_pair and pair_id is None:
        check_db = db.execute(sqlalchemy.text('select condition from pairs where pair_id=:pair_id'), pair_id=pair_id).fetchone()
        if check_db is not None and check_db[0] is not None:
            return check_db[0]

    # get the conditions with the number of people each, and randomize the order if some conditions have the same amount of people
    counts = db.execute(sqlalchemy.text('select condition, count(*) num from pairs group by condition order by num asc, random() asc')).fetchall()
    if len(counts) == 0: # no one has been assigned a condition
        return random.sample(CONDITIONS, 1)[0]
    elif len(counts) == len(CONDITIONS):
        # pick either the condition with the fewest people, or randomly select one of conditions with the fewest people
        return counts[0][0] 
    else: 
        # not all conditions are covered, get the list of conditions that have not been assigned, and sample from them
        included = {count[0] for count in counts}
        excluded = set(CONDITIONS) - included
        return random.sample(excluded, 1)[0]

# User colors
RED  = '#ff0000'
BLUE = '#0000ff'
GRAY = '#888888'

# App initialization
@app.before_first_request
def build_db():
    print('Initializing app...')
    db = get_db()

    # Load database schema
    db.execute(sqlalchemy.text('create table if not exists images (img_id serial primary key, path text unique, text text, poster text, affiliation text);'))
    db.execute(sqlalchemy.text('create table if not exists participants (user_id serial primary key, turk_id text unique, condition text, edge_case text, disconnected boolean, political_affiliation text, randomized_affiliation text, was_waiting boolean, work_complete boolean, party_affiliation text);'))
    db.execute(sqlalchemy.text('create table if not exists pairs (id serial primary key, right_worker integer references participants (user_id), left_worker integer references participants(user_id), obs_submitted boolean, mod_submitted boolean, work_ready boolean, mod_ready boolean, obs_ready boolean, last_mod_time decimal, last_obs_time decimal, last_mod_wait decimal, last_obs_wait decimal, disconnect_occurred boolean, create_time numeric, restarted boolean, joined_images text, condition integer)'))
    db.execute(sqlalchemy.text('create table if not exists observations(id serial primary key, pair_id integer references pairs(id), obs_text text, img_id integer, agreement_text text);'))
    db.execute(sqlalchemy.text('create table if not exists moderations(id serial primary key, decision text, img_id integer references images(img_id), pair_id integer references pairs(id), control_id integer references participants(user_id));'))
    db.execute(sqlalchemy.text('create table if not exists chosen_imgs(id serial primary key, img_id integer, pair_id integer);'))
    db.execute(sqlalchemy.text('create table if not exists control_imgs(id serial primary key, img_id integer, turk_id text);'))
    db.execute(sqlalchemy.text('create table if not exists images_revealed(id serial primary key, pair_id integer, img_index integer, temp_decision text);'))
    db.execute(sqlalchemy.text('create table if not exists consent(id serial primary key, turk_id text unique, response text);'))
    db.execute(sqlalchemy.text('create table if not exists exp_complete(id serial primary key, complete boolean unique);'))
    db.execute(sqlalchemy.text('create table if not exists mod_forms(id serial primary key, turk_id text unique, curr_index integer, responses text);'))
    db.execute(sqlalchemy.text('insert into participants(turk_id) values (\'robot\') WHERE NOT EXISTS (SELECT 1 FROM participants WHERE turk_id=\'robot\');'))
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
    cur.copy_expert('COPY images (img_id, path, text, poster, affiliation) from STDIN WITH CSV HEADER', f)
    conn.commit()

# Gets subset of all images to be displayed
def get_array_subset(array, num_vals, cannot_contain):
    assert len(array) - len(cannot_contain) >= num_vals
    assert NUM_IMAGES > 0

    # Separating political from non-political images
    pol_imgs = list()
    non_pol_imgs = list()
    for i in range(len(array)):
        if array[i][1] == 'n':
            non_pol_imgs.append(array[i])
        else:
            pol_imgs.append(array[i])

    subset = list()

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

# computes the delta between now and a give time for observers and moderators, and provides the strings needed as well
def compute_time_delta(in_time):
    time_now = time.time()
    delta = round(time_now - float(in_time), 1)
    out_str = str(delta) + ' seconds ago'

    return (delta, out_str)

# Calculates current state of worker
def get_worker_state(turk_id, last_wait_time, last_work_time):
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
def get_state_color(state):
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

def get_worker_state_color(turk_id, last_wait_time, last_work_time):
    state = get_worker_state(turk_id, last_wait_time, last_work_time)
    color = get_state_color(state)

    return(state, color)

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
    experiment_pol_html = ''
    for p in pairs:
        pair_id = p[0]
        obs_id = p[1]
        mod_id = p[2]

        #This is ordered by:
        # - general information about the pair
        #   - pair.work_ready
        # - moderator information (from participants then from pairs)
        #   - mod.turk_id
        #   - mod.edge_case
        #   - mod.condition
        #   - pair.mod_submitted
        #   - pair.last_mod_wait
        #   - pair.last_mod_time
        # - observer information (from participants then fom pairs)
        #   - obs.turk_id
        #   - obs.edge_case
        #   - obs.condition
        #   - pair.obs_submitted
        #   - pair.last_obs_wait
        #   - pair.last_obs_time
        incoming = db.execute(sqlalchemy.text('select pair.work_ready, mod.turk_id, mod.edge_case, mod.condition, pair.mod_submitted, pair.last_mod_wait, pair.last_mod_time, obs.turk_id, obs.edge_case, obs.condition, pair.obs_submitted, pair.last_obs_wait, pair.last_obs_time from pairs pair left_worker join participants mod on pair.mod_id=mod.user_id left_worker join participants obs on pair.obs_id=obs.user_id where pair.id=:pair_id'), pair_id=pair_id).fetchone()
        work_ready, mod_turk, mod_edge_case, mod_condition, mod_submitted, last_mod_wait_data, last_mod_work_ping_data, obs_turk, obs_edge_case, obs_condition, obs_submitted, last_obs_wait_data, last_obs_work_ping_data = incoming

        restarted = p[14] is not None
        print('{}, mod_condition: {}'.format(restarted, mod_condition))
        restart_style = 'background-color: #ed5e5e;' if restarted and mod_condition == CONDITION_EXP_VAL else ''
        pol_restart_style =  'background-color: #ed5e5e;' if restarted and mod_condition == CONDITION_POLITICAL_VAL else ''
        disconnect_style = '' if p[12] is None else 'opacity: 0.25; pointer-events: none;'
        done_text = done_class if mod_submitted is not None or obs_submitted is not None else ''

        conditions_match = mod_condition == obs_condition
        if not conditions_match and mod_condition is not None and obs_condition is not None:
            print('SOMETHING IS REALLY WRONG IN PAIRING PEOPLE - mod({}): {}, obs({}): {}'.format(mod_turk, mod_condition, obs_turk, obs_condition))

        # set work_ready_btn based on output
        if ((obs_id is None and mod_id is not None) or (obs_id is not None and mod_id is None)) and not experiment_complete and not restarted:
            work_ready_btn = ''
        else:
            work_ready_btn = '<button ' + ('disabled' if work_ready is not None else '') + ' onclick="markPairWorking(\'' + str(pair_id) + '\', this)">Start Work</button>'

        # Number of images revealed
        images_revealed_data = db.execute(sqlalchemy.text('select * from images_revealed where pair_id=:pair_id'), pair_id=pair_id).fetchall()
        images_revealed = 0 if images_revealed_data is None else len(images_revealed_data)

        # mods
        last_mod_wait_time, last_mod_wait = compute_time_delta(last_mod_wait_data) if last_mod_wait_data is not None else (None, None)
        last_mod_work_ping_time, last_mod_work_ping = compute_time_delta(last_mod_work_ping_data) if last_mod_work_ping_data is not None else (None, None)
        mod_state, mod_state_color = get_worker_state_color(mod_turk, last_mod_wait_time, last_mod_work_ping_time)if mod_id is not None else ('', get_state_color(''))
        mod_status_text = '<p style="margin-top:10px; font-size:10px;"><strong>State:</strong> <span style="color:{};">{}</span><br /><strong>Last wait ping:</strong> {}<br /><strong>Last work ping:</strong> {}<br /><strong>Images revealed:</strong> {}/{}<br/ ><strong>Edge case:</strong> {}</p>'.format(mod_state_color, mod_state, last_mod_wait, last_mod_work_ping, images_revealed, NUM_IMAGES, mod_edge_case) if mod_id is not None else ''

        #obs
        last_obs_wait_time, last_obs_wait = compute_time_delta(last_obs_wait_data) if last_obs_wait_data is not None else (None, None)
        last_obs_work_ping_time, last_obs_work_ping = compute_time_delta(last_obs_work_ping_data) if last_obs_work_ping_data is not None else (None, None)
        obs_state, obs_state_color = get_worker_state_color(obs_turk, last_obs_wait_time, last_obs_work_ping_time) if obs_id is not None else ('', get_state_color(''))
        obs_status_text = '<p style="margin-top:10px; font-size:10px;"><strong>State:</strong> <span style="color:{};">{}</span><br /><strong>Last wait ping:</strong> {}<br /><strong>Last work ping:</strong> {}<br /><strong>Images revealed:</strong> {}/{}<br/ ><strong>Edge case:</strong> {}</p>'.format(obs_state_color, obs_state, last_obs_wait, last_obs_work_ping, images_revealed, NUM_IMAGES, obs_edge_case) if obs_id is not None else ''

        if mod_condition == CONDITION_EXP_VAL or obs_condition == CONDITION_EXP_VAL:
            experiment_html = '<tr style="{}{}"><th {} scope="row">{}{}</th><td {}>{}{}</td><td {}>{}{}</td></tr>'.format(disconnect_style, restart_style, done_text, pair_id, work_ready_btn, done_text, mod_turk, mod_status_text, done_text, obs_turk, obs_status_text) + experiment_html
        elif mod_condition == CONDITION_POLITICAL_VAL or obs_condition == CONDITION_POLITICAL_VAL:
            experiment_pol_html = '<tr style="{}{}"><th {} scope="row">{}{}</th><td {}>{}{}</td><td {}>{}{}</td></tr>'.format(disconnect_style, pol_restart_style, done_text, pair_id, work_ready_btn, done_text, mod_turk, mod_status_text, done_text, obs_turk, obs_status_text) + experiment_pol_html

    num_pairs = len(db.execute(sqlalchemy.text('select * from pairs')).fetchall())

    return render_template('dashboard.html', control_html=control_html, experiment_html=experiment_html, experiment_pol_html=experiment_pol_html, experiment_complete=experiment_complete, num_pairs=num_pairs)


# Marks pair as ready to be moved to work page
@app.route("/" + MARK_WORK_READY_PAGE, methods=['POST'])
def mark_work_ready():
    json = request.json
    pair_id = json['pair_id']
    print('{}: setting work_ready=true in pairs where pair_id={}'.format(MARK_WORK_READY_PAGE, pair_id))
    db.execute(sqlalchemy.text('update pairs set work_ready=:true where id=:pair_id'), true=True, pair_id=pair_id)

    # Marking unpaired observers as finished working
    obs_id = db.execute(sqlalchemy.text('select obs_id from pairs where mod_id is NULL and id=:pair_id'), pair_id=pair_id).fetchone()
    if obs_id is not None and obs_id[0] is not None:
        db.execute(sqlalchemy.text('update participants set work_complete=TRUE where user_id=:obs_id'), obs_id=obs_id[0])
        db.execute(sqlalchemy.text('update pairs set mod_submitted=TRUE, obs_submitted=TRUE where id=:pair_id'), pair_id=pair_id)

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

# Begin a new trial session as part of the same experiment
@app.route("/" + NEW_TRIAL_PAGE, methods=['POST'])
def new_trial():
    # clear exp_complete value related to the previous trial
    db.execute(sqlalchemy.text('TRUNCATE TABLE exp_complete'))

    # restart pairing chain

    # make sure that first
    # experimental condition person is labelled "first"

    return jsonify(status='success')


# Restart experimental condition
@app.route('/restart_experimental', methods=['POST'])
def restart_experimental():
    # Mark all current pairs restarted
    print(request.json)
    json = request.json
    if json['which_condition'] == 'unaffiliated':
        cond = CONDITION_EXP_VAL
    elif json['which_condition'] == 'political':
        cond = CONDITION_POLITICAL_VAL

    full_pairs = db.execute(sqlalchemy.text(
        'SELECT obs.condition, mod.condition, pair.id'
        ' FROM pairs pair'
        ' JOIN participants obs ON obs.user_id=pair.obs_id'
        ' JOIN participants mod ON mod.user_id=pair.mod_id'));
    for obs_cond, mod_cond, cur_pair_id in full_pairs:
        if obs_cond == cond and mod_cond == cond:
            db.execute(sqlalchemy.text('update pairs set restarted=TRUE where id=:cur_id'), cur_id = cur_pair_id)

    # Set all currently unpaired moderators to 'Last' edge case
    unpaired_mods = db.execute(sqlalchemy.text('select mod_id from pairs where mod_id is not null and obs_id is null')).fetchall()
    for unpaired in unpaired_mods:
        db.execute(sqlalchemy.text('update participants set edge_case=:last where user_id=:unpaired and condition=:cond'), last='Last', unpaired=unpaired[0], cond=cond)

    return jsonify(status='success')

# Narrative page
@app.route("/" + NARRATIVE_PAGE)
def narrative():
    session.clear()
    excluded = {'ABMX8XUNPR3LP', 'ANFWGSQ8BQRZ', 'A2AAFWAAS9C1QC', 'A150GMV1YQWWB3', 'A2PWUACCQI97J8', 'A37XJVQF62ZYC', 'A3QLGMZOLGMBQ1', 'A24M9OW53CLT94', 'A34DR0CVUBDL1N', 'A2TDEX0T7XEPLU', 'A1AKL5YH9NLD2V', 'A2EHH2ZFIRF1BF', 'A10048W1LKR40', 'ANPBZZM3NR9B9', 'A2NLZCQZ9QOV4S', 'A2XPAKSCN9YUFZ', 'A2581F7TDPAMBQ', 'A3RYI5HXC2MJLN', 'A3W6T1WDYXMR3', 'A1C0H8G0YI15MN', 'A1JWKT0IS06YKL', 'A3SKEW89V5S0DI', 'A2BTDUJFLSBN8E', 'A1M3PLZBB92ZTP', 'A3EWTW55UCNAHG', 'A2NXHJ905WLGAA', 'A1OM5NWYYYJKQW', 'A37S96RT1P1IT2', 'A2ONILC0LZKG6Y', 'A1EKUJGMFDI1RZ', 'ABXI04K7467QI', 'A2E3TO92MCQ9XU', 'A1CH3TODZNQCES', 'A101IR0LIN81SL', 'AFIRH8MV85A4D', 'A1G2U62KJ13ZF0', 'A2WYCY1FMQOD5F', 'A2J18K5IUQ2K4G', 'A1Q68M0X4YXHKH', 'A1JKHGRDXU18PM', 'A26NGLGGFTATVN', 'A1BVG13MHBM1YD', 'A3L8LSM7V7KX3T', 'AWM9DEHK04MZ5', 'A1DNJ17PE2RYJZ', 'AB5T5XCK2ZD47', 'A1CSDIX05PK9V', 'A3VHDQR8A9JJ4F', 'A1VW8Y7XCV3DRW', 'A2VLTSW6CXIUMR', 'A14OPFM8OFA4WF', 'AHEVIE2NY1W1Z', 'A2ZZW6KME1FUDU', 'APGX2WZ59OWDN', 'A2CF2BD4Q0ZDJN', 'A31A4YKVSOYRVS', 'A1EXO9HRNQYHWC', 'A191V7PT3DQKDP', 'AUFOO8PU2BK37', 'A125AOX978LDG7', 'A125KW9P18V5Z1', 'A3J55BJGV95JKH', 'A110KENBXU7SUJ', 'A3R20AEJRD29WW', 'A11BSFO4LMHPXQ', 'A2X977GVQ6L90X', 'A1A8L6LU8E2YOA', 'A25CFVQND4A0EV', 'A20SL254675EOK', 'ALV4DAF8DIJ37', 'A26UIS59SY4NM6', 'A313JEGCVV2UES', 'A1E0X56CBY8X0L', 'A2541C8MY0BYV3', 'A1F8O6BA8AZTRF', 'A2R8IV2PWFTY00', 'A32HFMZVTLF1JG', 'A20MUNY2OLDCLC', 'A2HHWFGVV9UUC5', 'A3JGVZEXXELM3C', 'AMC1ATHYSMLXC', 'A2OVX9UW5WANQE', 'A234UW0G9PMSCC', 'A6EJ7EU0KMGPL', 'A3D70ANCSMGX5F', 'AVSLRTQLC2XK4', 'A1V1JNPU0KOA3X', 'AVNXCGTZQ1CFK', 'A175X5H642OD4W', 'A3QSFE6GKO157S', 'A1EITLFAMKA61U', 'A2ML0070M8FDK1', 'A1Q5RFVJKMZBEN', 'A1NFBKUYYVUYWF', 'A2INXY39KBM92F', 'A3CMWYLWMENHLZ', 'A1HAOXJVRYT43K', 'AJYGVMSBD5SJ0', 'AH9Y3W3PJGG32', 'A1F9KLZGHE9DTA', 'AWJUGWPCUGKEG', 'AJW3PL5UDH4BP', 'A16HSMUJ7C7QA7', 'A3JLE2LJ5I17E2', 'A2H5UA2MUBT4QX', 'AEX9MA72M10DC', 'AM8HWCZFGT1O5', 'A1L92Y6VBTRFP5', 'A2531UD0IGT731', 'A18QU0YQB6Q8DF', 'A12NO2MNOIREXA', 'A3B8DP6KHMP3OS', 'A1JPWEVV2SPZ7N', 'AEWGY34WUIA32', 'A2JDJFBKD3U830', 'AP9WIQ4P78XLH', 'A38NFX88VZDMJ3', 'A1F1OZ54G177D8', 'A1E77HZO63E334', 'A37WDOIQH6JM6V', 'A1NR3COO33J99C', 'A1LOD3LNX7FUPJ', 'A2P8PHVUWCQL7P', 'A272X64FOZFYLB', 'AIPHJXQEDNW9L', 'A4J4GGMKJ68L0', 'AKA49MPHUX5IK', 'A2PUL3ZDXOW0VZ', 'AUCHGHY1IKZZK', 'ADIXVUPICNIY4', 'A2FKEASJJHYISJ', 'A20CZCJPRP54G9', 'A1506T1PAYRT16', 'A17K1CHOI773VZ', 'A3R457FAWQXZN3', 'A12ATVBE1I4567', 'A2GZ00IMOT6L3X', 'AFA77JJROHLHZ', 'A1VAL7L9L79IN0', 'A2YUCJ28XANFOX', 'AJC3R52WI9ZNL', 'A25DP39XRZDLQM', 'A35TWG9VW1MB5S', 'A3LC6M2EMDBBXP', 'AKJ22H1NTVIQX', 'A2YLK83DQ6PA5Y', 'A244NGATA9ZFXX', 'A2YGOORS5N9RW8', 'AM02YP6440HLO', 'A3RS7UCO7CQ74R', 'A30DREP4GP5LNB', 'AETIZKQNUSBLB', 'A1RL6LTB8DSNVE', 'AKSJ3C5O3V9R', 'A5T9IFDZ3W4T6', 'A3908297ZI3LES', 'A2OR0PX4RNG2NU', 'AV22FQTJNBUZT', 'A3SD02HCW68EUL', 'A2NFEHOEDSC8F6', 'A1PMZUBGXFANCI', 'A23FMTVKQEYCMW', 'A26LOVXF4QZZCO', 'A3C7COPV48I37D', 'A1YSYI926BBOHW', 'A1P7G4500E2JCH', 'AKYXQY5IP7S0Z', 'A2ASBBDDJU1DZC', 'A3CXK1KSRGU27V', 'A3QC57KUVJP5EW', 'A1Y6HGDW6ZAYBY', 'A2WWYVKGZZXBOB', 'A1LSGYXKP6O1B8', 'A1NK84W9T83USS', 'A1PUHCEBSOWETV', 'A1N1EF0MIRSEZZ', 'A1TSD3O3C3ZUT6', 'A2OYD076D953N1', 'AA9V4NE8SOA4I', 'A23PQPECIUVKHC', 'AEQ8K4HBO323D', 'A1JVWOBGNA6KJT', 'A3OW5EFQ5QFD19', 'A154X03NKVZZL1', 'A19R9046KFC12H', 'A1NLJ1L4VCQYV2', 'A337MKRWW1YJSD', 'A22ABLVEI5EGPL', 'A2UUKFTD0VUX2S', 'A2H6K1XIK4LY7O', 'A2UHMLMFCP9J72', 'A2T3N9U2VPSFUM', 'A2YOVBJ9EXAI8W', 'A1160COTUR26JZ', 'A16H809DRDT4B9', 'A2ETY1O927Z1IF', 'ACAJFF4MF5S5X', 'A2I960JYUZ8KAV', 'A1SIUJEL2LS8UO', 'A2FARB7LA24AU8', 'AKVDY8OXNMQED', 'A3GXC3VG37CQ3G', 'A38IH5U8105J8', 'A34F2ESTZYTWRM', 'A22012GC5JSH0C', 'APO6KZZ79PO9Q', 'A3O5EU9QQV2OS1', 'A3R5OJR60C6004', 'A1IMO5XR05U7S5', 'A2SWQM5X54P1O5', 'AOKF2XWL4F5AJ', 'A3PH2PA5TISXYB', 'A3PK3QF2HEYZ0N', 'A1950D3SDRWBAH', 'A3FJCLBK3HF4PD', 'AZMOA8ONG0D2U', 'AUFUUD4WG9CVO', 'AYKZ9H4BNW810', 'A27PVIL93ZMY46', 'A3APKUC67F9IMW', 'AOB5RZ3WSAZPS', 'A1XJDQLDUMZF6R', 'A2TLN8489YGY81', 'A3G6L97AX9KR7F', 'A19T9RCL1INUT8', 'A3LT7W355XOAKF', 'AKSJ3C5O3V9RB', 'A147F5PJTHOB8A', 'A3BEZXV7X7EKI3', 'A2VRDE2FHCBMF8', 'A22AHPN2HZHFSV', 'A1RV2LERVS0A4H', 'A2SKY4RRWII0BF', 'A2RMJNF6IPI42F', 'ANNVWKERLZG9A', 'A2M45YGLOWMO4N', 'A3J0IAI8AJBGKX', 'A33UVS8TAJCHSN', 'A2O7AHH32GWNIS', 'AVX3SWFMBEPMZ', 'APRZ7BR8C0ZMQ', 'AG1BNU31ZP490', 'A2S75O867RJG0I', 'A2L26DMSVUEDP6', 'A2766O35JUD7LO', 'A1X8GO1B236KMK', 'A36ZLJPURT0ILP', 'A2UO3QJZNC2VOE', 'A4T4577P6JL6R', 'A273EH17NSJRH0', 'A1QKIA8XRNEXIG', 'A1FAK4VQ6WQUDC', 'AXMPSUNKUBEIL', 'A2EI075XZT9Y2S', 'AFU00NU09CFXE', 'APKFFVZKZJ6NZ', 'A2VY16N1O40VEL', 'A15EZCN5OCG62W', 'A1PYMROZ75S4FW', 'A3IYFX04J596X8', 'A20N1NK5X5S88F', 'A3UIDRGBV9NJWR', 'AYQAO6B91191T', 'A1LTJHPUTL7WM9', 'A15SUPIZ05ZFCD', 'A55CXM7QR7R0N', 'A1GCTKOPKUTW3G', 'AAQREZOK13OV7', 'AFN5VMMGYPF1I', 'A2YP22IYWPZWR0', 'AT6LDQNLKTUSE', 'A3KK1BNF5H0N1Z', 'A8RDXT4ZILHQT', 'A3LJ2FHESYV9QQ', 'A18FPXIJYCTETD', 'A3CH1Z6J9R38G9', 'A3FAF93BMDJLAL', 'AIEKCWYZTS41V', 'A2ZEUYRYGNHQ2Z', 'AU34T9OMHN4Z4', 'A36SM7QM8OK3H6', 'A1SX8IVV82M0LW', 'AK1Q45RF8A87Z', 'AEWPAZBYA7XE', 'A2FL477TMKC91L', 'A3TOUB8313BPVS', 'A1QEQOI98976S0', 'A1G42P7S1ROOD2', 'A3CSUQJ3WF1BKP', 'A207IHY6GERCFO', 'A30VAYXB85107X', 'A3IDAO8T75VO3Z', 'A1KCVYDWS80B7S', 'AU2RMH9IZP60M', 'AAKBYJD64R6K', 'A39Q4SNT7SRK94', 'A2VNK2H6USLQTK', 'A1EDMN0J522ATZ', 'A3HNL3252GJDD8', 'A2DDCDTHI8TBUT', 'A1TP0SGMUSJ34B', 'A1QA856X8I7GIZ', 'A2CK0OXMPOR9LE', 'A3774HPOUKYTX7', 'A53WVYONK6B9Q', 'A2CSENNI43N272', 'AP4750DK7PU1B', 'A320QA9HJFUOZO', 'A26BYNHCX4EBK6', 'A39C210BKD7YNN', 'A256FHXGSY0E5D', 'AAJDSGQRRSEPS', 'A1TGV7LT6LTIQU', 'AA4KKLIU4C3NY', 'A3TUCOUVSP9ZGY', 'A2TUUIV61CR0C7', 'A2FXD55FJV1RSV', 'A1MJVTR0PCKBWW', 'A2SBN9B6Q3DN2X', 'ABL3H3O3BI8ZD', 'A1DMXEJGJY02E1', 'A31NILFUEWAOSJ', 'A2M3KQ9CKP7YW', 'A30RAYNDOWQ61S', 'A10U1MDBII93UW', 'A5NE8TWS8ZV7B', 'A1WO011N7G89N', 'A2HAPKVM89N1OF', 'A2P065E9CYMYJL', 'A2WDF40FA670T9', 'A5EU1AQJNC7F2', 'AYFOAD75CRBKE', 'A3ZWMVK6GNTJ8', 'A2QJEE1E9XE4K5', 'A3G8OON0TDPN1E', 'A13FUEPWBCLBUY', 'AJYVLGIOG1CCH', 'A2YGAEODJ5SSF6', 'A2866TYG0D96LM', 'A1F34ZP6YNI98F', 'A3VDG4N48AVYGQ', 'A2YQAE441JMA7V', 'AZBH4LJ5SL456', 'A8KX1HFH8NE2Q', 'A2MD4K1YFYBLZN', 'A28XONYN8IBJIU', 'A1BBJJHGM0ADN7', 'A3LRSX7ECYPSF4', 'AESIFZEIVG1W5', 'AWIYSXEA51PFZ', 'A10BV0VOSJSJ6F', 'A29LYIS36PQSOF', 'A3LRZX8477TYYZ', 'A2VFEDAK5C1E1O', 'A3CQDCNYJAX2X3', 'AD14EQ9O9JKRI', 'A3AHCT6Q7A3Q23', 'A2ZNOMZ35LKY8Q', 'A3JSDZMBS8L87S', 'A4SC8G0149GEG', 'A1ZT30BGR3266K', 'A12R2U6TBB3OOG', 'A1WL3NZ50YEOWP', 'A37W3ZVEZMIH90', 'A1PT6264PIYFCI', 'A5J0OW727ZCWY', 'A1P6OXEJ86HQRM', 'A1QQQ7KKM896QY', 'A1UNBT94I82S8V', 'AAB92DK5SKQJC', 'A1RUURPQJ14A8X'}
    curs = db.execute(sqlalchemy.text('select turk_id, work_complete from participants')).fetchall()
    excluded = excluded.union({turk_id[0] for turk_id in curs if turk_id[1] is not None})

    turkId = request.args.get(TURK_ID_VAR)
    assignmentId = request.args.get(ASSIGNMENT_ID_VAR)

    already_completed = turkId in excluded

    preview = False
    if turkId is None:
        preview = True
    else:
        session[TURK_ID_VAR] = turkId
        session[ASSIGNMENT_ID_VAR] = assignmentId
        session[WAS_WAITING_VAR] = None
    
    print(turkId)
    print(preview)

    return render_template('narrative.html', turkId=turkId, preview=preview, num_images = NUM_IMAGES, dev=('true' if DEV else 'false'), already_completed=already_completed)

# Consent page
@app.route("/" + CONSENT_PAGE)
def consent():
    turkId = session[TURK_ID_VAR]
    db.execute(sqlalchemy.text('insert into consent(turk_id, response) VALUES(:turk_id, :no)'), turk_id=turkId, no='Unspecified')
    db.execute(sqlalchemy.text('update participants set work_complete=:complete where turk_id=:turk_id'), complete=True, turk_id=turkId)
    return render_template('consent.html')


# Done page
@app.route("/" + DONE_PAGE)
def done():
    turk_id = session.get(TURK_ID_VAR)
    consent = request.args.get(CONSENT_VAR)

    if consent is not None:
        print('{}: updating consent response=Yes where turk_id={}'.format(DONE_PAGE, turk_id))
        db.execute(sqlalchemy.text('update consent set response=:consent where turk_id=:turk_id'), consent=consent, turk_id=turk_id)

    return render_template('done.html', turk_id=turk_id, task_finished=True, assignment_id=session[ASSIGNMENT_ID_VAR])


# returns True if the person got paired, or False if a new pair was created
def check_edge_case(user_id):
    condition = db.execute(sqlalchemy.text('select condition from participants where user_id=:id'), id=user_id).fetchone()[0]
    obs_ids = db.execute(sqlalchemy.text('select pair.obs_id from pairs pair, participants obs where pair.mod_id IS NULL and pair.restarted IS NULL and pair.obs_submitted IS NULL and pair.obs_id=obs.user_id and obs.condition=:condition order by id asc'), condition=condition).fetchall()
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

@app.route("/" + WAIT_PAGE)
def wait():
    session['person_name'] = request.args.get('name')
    user_turk_id = session[TURK_ID_VAR]
    
    # check and see if the experiment has been completed
    complete = db.execute(sqlalchemy.text('select complete from exp_complete')).fetchone()
    experiment_complete = complete is not None and complete[0] is not None

    query_output = db.execute(sqlalchemy.text('select user_id, turk_id, disconnected, work_complete from participants where turk_id=:turk_id'), turk_id=user_turk_id).fetchone()
    
    if query_output is None:
        user_pid = None
        worker_exists = False
        user_disconnected = False
        user_work_complete = False
    else:
        user_pid, user_db_turk_id, user_disconnected, user_work_complete = query_output
        worker_exists = True
        # Checking if user is trying to rejoin after a disconnect
        if user_disconnected is not None:
            return redirect('/disconnect?turkId=%s&dc=you' % turk_id)
        
        # Check if user has already finished their task, moving them directly to Done page if so
        if user_work_complete is not None:
            return redirect('/done?consent=pilot')

    if experiment_complete:
        task_finished = True if worker_exists else False
        return render_template('done.html', turk_id=user_turk_id, task_finished=task_finished, assignment_id=session[ASSIGNMENT_ID_VAR])
    elif worker_exists:
        return redirect(url_for(WORK_PAGE))
    else: 
        # See if there's a URL parameter, otherwise assign condition
        
        # unclear what this is for
        db.execute(sqlalchemy.text('update mod_forms set curr_index=0, responses=\'\' where turk_id=:uid'), uid=user_pid)

        polArg = request.args.get('pol')
        partyArg = request.args.get('party')
        if polArg is None:
            affiliation = 'Unspecified'
        else:
            affiliation = urllib.parse.unquote(polArg)
        if partyArg is None:
            party = 'Unspecified'
        else:
            party = urllib.parse.unquote(partyArg)

        url_cond = request.args.get(CONDITION_VAR)
        if url_cond is None or url_cond not in CONDITIONS:
            pair_condition = get_random_condition(True, None)
        session[CONDITION_VAR] = pair_condition
        
        print('pid: {}'.format(user_pid))
        result = db.execute(sqlalchemy.text('insert into participants(turk_id, political_affiliation, was_waiting, party_affiliation) VALUES(:uid, :affiliation, :waiting, :party) '), uid=user_turk_id, cond=pair_condition, affiliation=affiliation, waiting=True, party=party)
        db.execute(sqlalchemy.text('insert into mod_forms(turk_id, curr_index, responses) VALUES(:uid, 0, \'\')'), uid=user_pid)

        user_pid = db.execute(sqlalchemy.text('select user_id from participants where turk_id=:uid'), uid=user_turk_id).fetchone()[0]
        session['pid'] = user_pid
        img_rows = db.execute(sqlalchemy.text('select img_id from images order by random()')).fetchall()
        pair_joined_images = '|'.join([str(img_id[0]) for img_id in img_rows])

        if PILOT_NOW:
            # everyone gets assigned a robot partner, so we set that up
            right_worker_id = db.execute(sqlalchemy.text('select user_id from participants where turk_id=:uid'), uid='robot').fetchone()[0]
            db.execute(sqlalchemy.text('insert into pairs(left_worker, right_worker, work_ready, create_time, joined_images, condition) VALUES(:you, :right_worker, TRUE, :time, :imgs, :cond)'), you=user_pid, right_worker=right_worker_id, time=time.time(), imgs=pair_joined_images, cond=pair_condition)
            pair_id = db.execute(sqlalchemy.text('select id from pairs where left_worker=:you'), you=user_pid).fetchone()[0]
            session[POSITION_VAR] = POSITION_LEFT_WORKER
        else:
            # if there are no empty pairs, you become an empty pair and wait, otherwise you join an empty pair
            num_unpaired = db.execute(sqlalchemy.text('select count(*) from pairs where right_worker=NULL')).fetchone()
            if num_unpaired == 0:
                db.execute(sqlalchemy.text('insert into pairs(left_worker, create_time, joined_images, condition) VALUES(:you, :time, :imgs, :cond)'), you=user_pid, right_worker=right_worker_id, time=time.time(), imgs=pair_joined_images, cond=pair_condition)
                pair_id = db.execute(sqlalchemy.text('select id from pairs where left_worker=:you'), you=user_pid).fetchone()[0]
                session[POSITION_VAR] = POSITION_RIGHT_WORKER
            else: 
                right_worker_id = user_pid
                db.execute(sqlalchemy.text('update pairs set (right_worker, work_ready) values (:right_worker, TRUE) from (select id from pairs order by create_time asc limit 1) as sub where pairs.id=sub.id'), right_worker=right_worker_id).fetchone()
                pair_id = db.execute(sqlalchemy.text('select id from pairs where right_worker=:you'), you=user_pid).fetchone()[0]
                session[POSITION_VAR] = POSITION_RIGHT_WORKER

        session['pair_id'] = pair_id

        return render_template('wait.html', pair_id=pair_id)


# You or your partner was previously disconnected, ending task
@app.route('/disconnect')
def do_disconnect():
    turk_id = request.args.get('turkId')
    db.execute(sqlalchemy.text('update participants set work_complete=TRUE where turk_id=:turk_id'), turk_id=turk_id)

    disconnector = request.args.get('dc')
    return render_template('disconnect.html', dc=disconnector, assignment_id=session[ASSIGNMENT_ID_VAR])

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

    if mod_ready[0] is None or obs_ready[0] is None: # Not ready
        return jsonify(status='not ready')
    else: # Both ready
        return jsonify(status='ready')

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

# Submits moderator decisions to database
@app.route("/" + SUBMIT_MODS_PAGE, methods=['POST'])
def accept_moderations():
    json = request.json

    pair_id = json['pair_id']
    img_ids = json['img_ids']
    decisions = json['decisions']
    turk_id = json['turk_id']

    for i in range(NUM_IMAGES):
        if pair_id == 0: # Worker was in control group
            print('{}: insert decision={} and img_id={} into moderations'.format(SUBMIT_MODS_PAGE, decisions[i], img_ids[i]))
            user_id = db.execute(sqlalchemy.text('select user_id from participants where turk_id=:turk_id'), turk_id=turk_id).fetchone()[0]
            db.execute(sqlalchemy.text('insert into moderations(decision, img_id, control_id) VALUES(:decision, :img_id, :user_id)'),decision=decisions[i], img_id=img_ids[i], user_id=user_id)
        else: # Worker was in experimental group
            print('{}: insert decision={}, img_id={}, and pair_id={} into moderations'.format(SUBMIT_MODS_PAGE, decisions[i], img_ids[i], pair_id))
            db.execute(sqlalchemy.text('insert into moderations(decision, img_id, pair_id) VALUES(:decision, :img_id, :pair_id)'),decision=decisions[i], img_id=img_ids[i], pair_id=pair_id)

    print('{}: set mod_submitted=True where id={} in pairs'.format(SUBMIT_MODS_PAGE, pair_id))
    db.execute(sqlalchemy.text('update pairs set mod_submitted=:sub where id=:pair_id'), sub=True, pair_id=pair_id)
    return jsonify(status='success')

# Ping server to acknowledge that you're still connected, check if partner is still connected
@app.route('/ping', methods=['POST'])
def do_ping():
    pair_id = request.json['pair_id']
    role = request.json['role']
    check_dc = request.json['check_dc']
    turk_id = request.json['turk_id']

    curr_time = time.time()
    if role == 'mod':
        db.execute(sqlalchemy.text('update pairs set last_mod_time=:time where id=:pair_id'), time=curr_time, pair_id=pair_id)
        last_time = db.execute(sqlalchemy.text('select last_obs_time from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]
        partner_finished = db.execute(sqlalchemy.text('select obs_submitted from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0] is not None
    else:
        db.execute(sqlalchemy.text('update pairs set last_obs_time=:time where id=:pair_id'), time=curr_time, pair_id=pair_id)
        last_time = db.execute(sqlalchemy.text('select last_mod_time from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0]
        partner_finished = db.execute(sqlalchemy.text('select mod_submitted from pairs where id=:pair_id'), pair_id=pair_id).fetchone()[0] is not None

    # Moderator form state
    mod_form = db.execute(sqlalchemy.text('select curr_index, responses from mod_forms where turk_id=:turk_id'), turk_id=turk_id).fetchone()
    curr_index = mod_form[0]
    responses = mod_form[1]

    if check_dc == 'yes':
        if last_time is None:
            return jsonify(partner_status='disconnected', curr_index=curr_index, responses=responses)
        elif curr_time - float(last_time) >= TIMEOUT and not partner_finished:
            return jsonify(partner_status='disconnected', curr_index=curr_index, responses=responses)
        else:
            return jsonify(partner_status='connected', curr_index=curr_index, responses=responses)
    else:
        return jsonify(partner_status='connected', curr_index=curr_index, responses=responses)

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
def get_user_photo(randomize):
    pol = get_user_pol(randomize)
    if pol == 'Republican':
        return 'images/rep.png'
    elif pol == 'Democrat':
        return 'images/dem.png'
    else:
        return 'NULL'
def get_user_name(randomize):
    pol = get_user_pol(randomize)
    if pol == 'Republican':
        return 'a Republican'
    elif pol == 'Democrat':
        return 'a Democrat'
    else:
        return 'neither a Democrat nor a Republican'
def get_user_color(randomize):
    pol = get_user_pol(randomize)
    if pol == 'Republican':
        return RED
    elif pol == 'Democrat':
        return BLUE
    else:
        return GRAY
def get_obs_color():
    obs_pol = get_obs_pol()
    if obs_pol is not None:
        if 'neither' in obs_pol:
            return GRAY
        elif 'Democrat' in obs_pol:
            return BLUE
        elif 'Republican' in obs_pol:
            return RED
    else:
        return ''

def get_obs_pol():
    turk_id = session[TURK_ID_VAR]
    get_user_pol(True)
    incoming =  db.execute(sqlalchemy.text('select obs.edge_case, obs.randomized_affiliation from pairs, participants obs, participants mod where pairs.obs_id=obs.user_id and pairs.mod_id=mod.user_id and mod.turk_id=:turk_id;'), turk_id=turk_id).fetchone()
    if incoming is not None:
        edge_case, affiliation = incoming
        if edge_case != 'Last':
            if affiliation == 'Republican':
                return 'a Republican'
            elif affiliation == 'Democrat':
                return 'a Democrat'
            elif affiliation == 'Independent':
                return 'neither a Democrat nor a Republican'
    else:
        return '';

def get_user_pol(randomize):
    # politicizing = True # For debug
    # if politicizing:
    turk_id = session[TURK_ID_VAR]
    print('randomized variable: {}'.format(randomize))
    print('{} should be randomized: {}'.format(turk_id, session[JOB_VAR] == JOB_OBS_VAL))
    if randomize:
        prev_rand = db.execute(sqlalchemy.text('select randomized_affiliation from participants where turk_id=:turk_id'), turk_id=turk_id).fetchone()[0]
        if prev_rand is not None:
            return prev_rand
            # if prev_rand == 'Republican':
            #     return ''
            # elif prev_rand == 'Democrat':
            #     return BLUE
            # else:
            #     return GRAY

        val = random.uniform(0, 1)

        if val < 0.333:
            rand_aff = 'Republican'
            # rand_color = RED
        elif val < 0.667:
            rand_aff = 'Democrat'
            # rand_color = BLUE
        else:
            rand_aff = 'Independent'
            # rand_color = GRAY

        db.execute(sqlalchemy.text('update participants set randomized_affiliation=:rand_aff where turk_id=:turk_id'), rand_aff=rand_aff, turk_id=turk_id)
        return rand_aff;
    else:
        affiliation = db.execute(sqlalchemy.text('select party_affiliation from participants where turk_id=:turk_id'), turk_id=turk_id).fetchone()[0]
        return affiliation

        # if affiliation == 'Republican':
        #     return RED
        # elif affiliation == 'Democrat':
        #     return BLUE
        # else:
        #     return GRAY
    # else:
    #     return '#{:06x}'.format(random.randint(0, 256**3))



# Work page where observing/moderation occurs
@app.route("/" + WORK_PAGE)
def work():

    # posts=[
    #     {"img_id":9,"path":"static/images/c_1279.png","text":"They take yourjob and money! Stop illegal immigration!","poster":"Stop A.I.","affiliation":"c"},
    #     {"img_id":10,"path":"static/images/l_3088.png","text":"Newsblog about social injustice in the US. Join us and stay informed!\nWilliams&Ka|vin","poster":"Williams&Kalvin","affiliation":"l"},
    #     {"img_id":11,"path":"static/images/c_1292.png","text":"This time you need to stay at home!","poster":"Stop Refugees","affiliation":"c"},
    #     {"img_id":15,"path":"static/images/l_796.png","text":"It's time for Changes in Black Community! Stay together brother let us be\ntogether here!","poster":"Williams&Kalvin","affiliation":"l"},
    #     {"img_id":40,"path":"static/images/c_24.png","text":"TAG YOUR PHOTOS WITH #TXagainst Send us the reason why don't you\nwant illegals in Texas.\nComments, photos, and videos are welcomed!","poster":"rebeltexas","affiliation":"c"},
    #     {"img_id":74,"path":"static/images/l_374.png","text":"Join us because we care. Black matters.","poster":"Black Matters","affiliation":"l"},
    #     {"img_id":84,"path":"static/images/n_26.png","text":"Home of the Brave. Support our Veterans! Click Learn More! Veterans USA (\n@veterans GovSpending","poster":"american.veterans","affiliation":"n"},
    #     {"img_id":102,"path":"static/images/n_356.png","text":"Such a beautiful day! Such a beatiful view!","poster":"L for life","affiliation":"n"},
    #     {"img_id":124,"path":"static/images/n_3002.png","text":"Hallelujah! Ministering and uniting all Black congregations Worldwide. Join\nour non denominational group!","poster":"Black_Baptist_church","affiliation":"n"},
    #     {"img_id":128,"path":"static/images/n_3407.png","text":"Free online player! Jump in the world of free music! Click and download for ur\nbrowser Unlimited, free and rapid app for you - listen music online on ur\nFacebook! musicfb.info FaceMusic Stop A.|.","poster":"Stop A.I.","affiliation":"n"}
    # ]
    # # from random import shuffle
    # # random.shuffle(posts)
    # posts=json.dumps(posts)

    # users={
    #     "left_worker":{
    #         "name":"John Doe",
    #         "affiliation":"Democrat",
    #         "is_user":"yes"
    #     },
    #     "right_worker":{
    #         "name":"Jane Doe",
    #         "affiliation":"Republican",
    #         # "is_user":"yes"
    #     }
    # }

    # pair_id = 'ijodwa23s' # get pair's UUID
    # turk_id = '39ju0fjes' # get user's UUID
    # pairwise_mode = 2 # get mode from user's db entry


    # I'm gonna make a bunch of assumptions here:
    # * variables prefixed with "user_" relate to the person for whom this page is being rendered
    # * variables prefixed with "partner_" relate to the paired person, but are important for rendering a complete work page
    # * variables prefixed with "pair_" relate to the pair itself (both 'user_' and 'partner_')
    # * we set the image order on the wait page
    # * we set the position 'user_' is in on the wait page
    # * we set the condition for the pair on the wait page


    user_turk_id = session[TURK_ID_VAR]
    user_job = session[POSITION_VAR]
    pair_condition = session[CONDITION_VAR]
    session[WAS_WAITING_VAR] = None
    user_position = session[POSITION_VAR]
    was_waiting = db.execute(sqlalchemy.text('update participants set was_waiting=:was_waiting where turk_id=:uid'), was_waiting=None, uid=user_turk_id)
    user_pid = session['pid']
    pair_id = session['pair_id']
    # user_color = get_user_color(job == JOB_OBS_VAL)
    # user_name = get_user_name(job == JOB_OBS_VAL)
    # user_pic = get_user_photo(job == JOB_OBS_VAL)
    # mod_banner = get_obs_pol() if 'exp' in condition and job == JOB_MOD_VAL else ''
    # banner_color = get_obs_color() if 'exp' in condition and job == JOB_MOD_VAL else ''

    # If experiment is complete and worker is an unpaired moderator, move them to the control condition
    # If experiment is complete and worker is an unpaired observer, move them to the Done page
    complete = db.execute(sqlalchemy.text('select complete from exp_complete')).fetchone()
    experiment_complete = complete is not None and complete[0] is not None

    # unpaired_mod = db.execute(sqlalchemy.text('select id from pairs where mod_id=:turk_id and obs_id is NULL'), turk_id=pid).fetchone()
    # if experiment_complete and unpaired_mod is not None:
    #     db.execute(sqlalchemy.text('update participants set edge_case=:case where turk_id=:turk_id'), case='Last', turk_id=turkId)

    # Constructing room name as concatenation of moderator and observer IDs (only in experimental condition)
    print(pair_condition)
    create_time = db.execute(sqlalchemy.text('select create_time from pairs where id=:pair_id'), pair_id=pair_id).fetchone();
    room_name = 'pair-{}-{}'.format(pair_id, create_time) if pair_condition > 0 else ''

	# Getting all image URLs in database
    rows = db.execute(sqlalchemy.text('select row_to_json(images) from images order by random()')).fetchall()
    posts = [post[0] for post in rows]
    pair = db.execute(sqlalchemy.text('select left_worker, right_worker from pairs where id=:pair_id'), pair_id=pair_id).fetchone()
    if (pair[0] == user_pid and user_position != 'l') or (pair[1] == user_pid and user_position != 'r'):
        print('THERE IS SOMETHING WRONG GETTING USER POSITION')
    else:
        left_worker = db.execute(sqlalchemy.text('select turk_id, political_affiliation from participants where user_id=:user_id'), user_id=pair[0]).fetchone()
        right_worker = db.execute(sqlalchemy.text('select turk_id, political_affiliation from participants where user_id=:user_id'), user_id=pair[1]).fetchone()

        users={"left_worker":{"name": left_worker[0], "affiliation": left_worker[1]}, "right_worker": {"name": right_worker[0], "affiliation": right_worker[1]}}
        if PILOT_NOW and users['right_worker']['affiliation'] is None and users['right_worker']['name'] == 'robot':
            if session.get('robot_affiliation') is None and session.get('robot_name') is None:
                session['robot_affiliation'] = random.sample(['Conservative', 'Liberal'], 1)[0]
                session['robot_name'] = names.get_full_name()
            users['right_worker']['affiliation'] = session['robot_affiliation']
            users['right_worker']['name'] = session['robot_name']
            users['left_worker']['name'] = session['person_name']
        if user_position == 'l':
            users["left_worker"]["is_user"] = 'yes'
        elif user_position == 'r':
            users["right_worker"]["is_user"] = 'yes'

    # Set last time right_worker before work begins
    curr_time = time.time()
    # if page == 'moderation':
    #     db.execute(sqlalchemy.text('update pairs set last_mod_time=:time where id=:pair_id'), time=curr_time, pair_id=pair_id)
    #     last_time = db.execute(sqlalchemy.text('select last_obs_time from pairs where id=:pair_id'), pair_id=pair_id).fetchone()
    # else:
    #     db.execute(sqlalchemy.text('update pairs set last_obs_time=:time where id=:pair_id'), time=curr_time, pair_id=pair_id)
    #     last_time = db.execute(sqlalchemy.text('select last_mod_time from pairs where id=:pair_id'), pair_id=pair_id).fetchone()

    return render_template('new_work.html', posts=posts, users=users, pair_id=pair_id, turk_id=user_turk_id, pairwise_mode=pair_condition)