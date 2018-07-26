from flask import Flask, session, redirect, url_for, escape, request, render_template, jsonify
import random
import base64
import sqlite3
from flask import g

app = Flask(__name__)

app.secret_key = b'\xbfEdVSb\xc6\x91Q\x02\x1c\xa7cN\xba$'
app.dev = True

DATABASE = './database.db'

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

with app.app_context():
    db = get_db()
    with app.open_resource('db.schema', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()
    out = db.execute('select count(*) from images')
    count = out.fetchall()[0][0]
    if count == 0:
        db.execute('insert into images(img_path) VALUES("images/img.jpg")')
        db.execute('insert into images(img_path) VALUES("images/img2.jpg")')
        db.execute('insert into images(img_path) VALUES("images/img3.jpg")')
        db.commit()

# @app.after_request
# def commit_db():
#     with app.app_context():
#         db = get_db()
#         db.commit()

def get_condition():
    options = ['control', 'experimental']
    if 'condition' not in session:
        if request.args.get('condition') in options:
            session['condition'] = request.args.get('condition')
        else:
            session['condition'] = options[random.getrandbits(1)]
    
    return session['condition']

def get_job(step, condition):
    if step == 'wait1' and condition == 'experimental':
        return 'observe'
    
    return 'moderate'

def supposed_to_be_here(from_func, step, condition):
    print(condition)
    if app.dev:
        return True 

    if from_func == 'router' and step != 'wait1' and step != 'wait2':
        print('\tcoming from router and wrong step')
        return False
    
    if from_func == 'work':
        if step is not 'work1' and condition == 'control':
            print('\tcoming from work and control condition and observation job')
            return False
        if condition == 'experimental' and step != 'work1' and step != 'work2':
            print('\tcoming from work and experimental condition and observation job but large step')
            return False

    return True

def get_page_values(job, step, condition):
    color = 'white'
    page = 'moderation'
    reason = ''
    print('page values: {}, {}, {}'.format(job, step, condition))
    if condition == 'control':
        reason = 'you are in the control condition'
        print('page values control')
    elif condition == 'experimental' and step == 'work1':
        page = 'observation'
        reason = 'you are in the experimental condition and this is the first time you have visited'
        print('page values experimental1')
    elif condition == 'experimental' and step == 'work2':
        reason = 'you are in the experimental condition and this is the second time you have visited'
        print('page values experimental2')
    else:
        color = 'red'
        page = 'error'
        reason = 'you are not supposed to be here anymore'
        print('page values error')

    return color, page, reason

@app.route("/error")
def error():
    turkId = request.args.get('turkId')
    step, condition = query_db('select b.state, a.condition from participants as a, participants_state as b where b.turk_id=? and a.turk_id=b.turk_id', [turkId], one=True) 
    print('ERROR PAGE - step: {}, condition: {}'.format(step, condition))
    color, page, reason = get_page_values('', '', '')
    return render_template('base.html', color=color, page=page, reason=reason)

@app.route("/clear")
def clear():
    # clear the session if I tell you to
    if app.dev:
        session.clear()
        return redirect(url_for('wait', turkId='jts_test'))
    else:
        return redirect(url_for('error', turkId='jts_test'))

@app.route("/wait")
def wait():
    if app.dev:
        session.clear()

    uid = request.args.get('turkId')
    check = query_db('select turk_id from participants where turk_id=?', [uid], one=True)
    if check is None:
        options = ['control', 'experimental']

        # for testing purposes
        if request.args.get('condition') and app.dev:
            session['condition'] = request.args.get('condition')
        else:
            session['condition']=random.sample(options, 1)[0]
        # session['condition'] = 'experimental'
        query_db('insert into participants(turk_id, condition) VALUES(?, ?)', [uid, session['condition']], one=True)
        query_db('insert into participants_state(turk_id, state) VALUES(?, ?)', [uid, 'wait1'], one=True)
        if session['condition'] == 'experimental':
            # check the DB for this user
            t = query_db('select count(obs_id) from pairs', one=True)
            count = t[0]
            if count == 0:
                query_db('insert into pairs(mod_id) VALUES(?)', [uid], one=True)
            else:
                q = query_db('select * from pairs where obs_id!=? and mod_id is null limit 1', [uid], one=True)
                print(q)
                if q is not None:
                    name = q[1]
                    query_db('update pairs set mod_id=? where obs_id=?', [uid, name], one=True)
                else:
                    query_db('insert into pairs(mod_id) VALUES(?)', [uid], one=True)
            
            query_db('insert into pairs(obs_id) VALUES(?)', [uid], one=True)
    else:
        query_db('update participants_state set state=? where turk_id=?', ['wait2', uid], one=True)
            

    return render_template('base.html', color='gray', page='waiting', reason='')

@app.route('/dashboard')
def dashboard():
    participants=query_db('select * from participants', one=False)
    control = [p for p in participants if p[2]=='control']
    experiment = [p for p in participants if p[2]=='experimental']
    pairs = []
    for p in experiment:
        q = query_db('select mod_id from pairs where obs_id=?', [p[1]], one=True)
        if q is None:
            pairs.append((q,))
        else: 
            pairs.append(q)
    
    exp_pairs = [a + b for a, b in zip(experiment, pairs)]

    control_html = ''.join(['<tr><th scope="row">{}</th><td>{}</td></tr>'.format(c[0], c[1]) for c in control])
    experiment_html = ''.join(['<tr><th scope="row">{}</th><td>{}</td><td>{}</td></tr>'.format(c[0], c[3], c[1]) for c in exp_pairs])

    return render_template('dashboard.html', control_html=control_html, experiment_html=experiment_html)

@app.route("/submit_mods", methods=['POST'])
def accept_moderations():
    json = request.get_json()

@app.route("/")
def index():
    turkId = request.args.get('turkId')
    print(turkId)
    step, condition = query_db('select b.state, a.condition from participants as a, participants_state as b where b.turk_id=? and a.turk_id=b.turk_id', [turkId], one=True)
    if app.dev:
        session['step'] = request.args.get('step')
        session['condition'] = condition 
    
    print('ROUTER PAGE - step: {}, condition: {}'.format(step, condition))
    
    print(supposed_to_be_here('router', step, condition))
    if not supposed_to_be_here('router', step, condition):
        print('ERROR /')
        return redirect(url_for('error', turkId=turkId))
    
    job = get_job(step, condition) if not app.dev else request.args.get('job')

    # need logic here for figuring out which room people get routed to

    print('\trouting to {}'.format(job))
    # return redirect(url_for('work', p=base64.urlsafe_b64encode(job.encode()).decode('ascii') if not app.dev else job, turkId=turkId))
    session['turkId'] = turkId
    session['job'] = base64.urlsafe_b64encode(job.encode()).decode('ascii') if not app.dev else job
    return redirect(url_for('work'))

@app.route("/work") 
def work():
    job = base64.urlsafe_b64decode(session['job']).decode('ascii') if not app.dev else session['job']
    print(job)
    message = 'WORK PAGE - '
    # turkId = request.args.get('turkId')
    turkId = session.get('turkId')
    step, condition = query_db('select b.state, a.condition from participants as a, participants_state as b where b.turk_id=? and a.turk_id=b.turk_id', [turkId], one=True) if not app.dev else session['step'], session['condition']
    if step == 'wait1' and job == 'observe':
        query_db('update participants_state set state=? where turk_id=?', ['work1', turkId])
    elif step == 'wait1' and job == 'moderate' and condition == 'control':
        query_db('update participants_state set state=? where turk_id=?', ['work1', turkId])
    elif step == 'wait2' and job == 'moderate':
        query_db('update participants_state set state=? where turk_id=?', ['work2', turkId])
    step, condition = query_db('select b.state, a.condition from participants as a, participants_state as b where b.turk_id=? and a.turk_id=b.turk_id', [turkId], one=True)

    # You shouldn't be able to do anything else
    if not supposed_to_be_here('work', step, condition):
        print('ERROR /work')
        return redirect(url_for('error', turkId=turkId))

    print(job)
    if job == 'moderate':
        # assert(session['step'] == 2 or session['step'] == 4)
        obs, mod = query_db('select obs_id, mod_id from pairs where mod_id=?', [turkId], one=True)
        print(message + 'moderation task')
    elif job == 'observe':
        # assert(session['step'] == 2 and session['condition'] == 'experimental')
        obs, mod = query_db('select obs_id, mod_id from pairs where obs_id=?', [turkId], one=True)
        # query_db('select obs_id||mod_id from pairs where obs_id=?', request.args.get('turkId'), one=True)
        print(message + 'observation task')
    else:
        print('ERROR /work 2')
        return redirect(url_for('error', turkId=turkId))
    
    color, page, reason = get_page_values(job, step, condition)
    print('obs|mod: {}|{}'.format(obs, mod))
    room_name = '{}|{}'.format(obs, mod)

    print(room_name)
    return render_template('base.html', color=color, page=page, reason=reason, room_name=room_name)
