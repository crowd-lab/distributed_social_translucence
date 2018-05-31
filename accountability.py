from flask import Flask, session, redirect, url_for, escape, request, render_template
import random
app = Flask(__name__)

app.secret_key = b'\xbfEdVSb\xc6\x91Q\x02\x1c\xa7cN\xba$'

def setup():
    return request.args.get('condition')

@app.route("/error")
def error():
    color='red'
    page='error'
    reason='you are not supposed to be here anymore'
    return render_template('base.html', color=color, page=page, reason=reason)

@app.route("/moderate")
def moderate():
    # You shouldn't be able to do anything else
    if 'seen' in session and session['seen'] != 'experimental_observed':
        return redirect(url_for('error'))

    session['seen'] = '{}_done'.format(session['condition'])
    color = 'green'
    page = 'moderation'
    reason = 'you are in the {} condition{}'.format(session['condition'], 'and this is the second time you have visited' if session['condition'] == 'experimental' else '')
    return render_template('base.html', color=color, page=page, reason=reason)

@app.route("/observe")
def observe():
    # You shouldn't be able to do anything else
    if 'seen' in session and session['seen'] != 'experimental_observed':
        return redirect(url_for('error'))

    if session['condition'] == 'control':
        return redirect(url_for('error'))

    session['seen'] = '{}_observed'.format(session['condition'])
    color = 'orange'
    page = 'observation'
    reason = 'you are in the {} condition{}'.format(session['condition'], 'and this is the first time you have visited')
    target='moderate'
    return render_template('base.html', color=color, page=page, reason=reason, target=target)

@app.route("/clear")
def clear():
    # clear the session if I tell you to
    if request.args.get('pw') == 'jts':
        session.clear()
        # if we didn't set condition in the URL, pick one randomly
        session['condition']=request.args.get('condition') if request.args.get('condition') in ['control', 'experimental'] else ['control', 'experimental'][random.getrandbits(1)]
        return redirect(url_for('index'))
    else:
        color='pink'
        page='clear_error'
        reason='your clear password is wrong'
        return render_template('base.html', color=color, page=page, reason=reason) 

@app.route("/")
def index():
    # You shouldn't be able to do anything else
    if 'seen' in session and session['seen'] != 'experimental_observed':
        return redirect(url_for('error'))

    # if we didn't set condition in the URL, and it's not stored in the session, pick one randomly
    if 'condition' not in session:
        session['condition']=request.args.get('condition') if request.args.get('condition') in ['control', 'experimental'] else ['control', 'experimental'][random.getrandbits(1)]

    color = 'blue'
    page = 'waiting'
    reason = 'you have accepted the HIT and we are waiting for an image submission'
    if session['condition'] == 'control':
        target = 'moderate'
    elif session['condition'] == 'experimental':
        target = 'observe'

    return render_template('base.html', color=color, page=page, reason=reason, target=target)