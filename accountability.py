from flask import Flask, session, redirect, url_for, escape, request, render_template
app = Flask(__name__)

app.secret_key = b'\xbfEdVSb\xc6\x91Q\x02\x1c\xa7cN\xba$'
def control_condition():
    return 'moderation task'

def intervention_condition():
    return 'observation_task'

def incorrect_condition():
    return 'you\'re not supposed to be here'

@app.route("/")
def hello():
    control = True if request.args.get('control') == 'True' else False
    print('control: {}'.format(control))
    print('seen: {}'.format('seen' in session))
    print('not seen: {}'.format('seen' not in session))
    print('session: {}'.format(session.keys()))

    color = ''
    page = ''
    reason = ''

    # clear the session if I tell you to
    if request.args.get('clear') == 'jts':
        session.clear()
        color='pink'
        page='clearing'
        reason='because of your URL parameter'
    # You shouldn't be able to do anything else
    elif 'seen' in session and session['seen'] != 'experimental_observed':
        color='red'
        page='error'
        reason='you are supposed to be here anymore'
    else:
        # This is the control condition
        if control:
            color = 'green'
            page = 'moderation'
            reason = 'you are in the control condition'
            session['seen'] = 'control_done'
        
        # This is the experimental condition
        if not control:
            # You should be routed to Observation
            if 'seen' not in session:
                session['seen'] = 'experimental_observed'
                color = 'yellow'
                page = 'observation'
                reason='you are in the experimental condition and this is the first time you have visited'
            # Then you should be routed to moderation
            elif 'seen' in session and session['seen'] == 'experimental_observed':
                session['seen'] = 'experimental_moderated' 
                color='orange'
                page='moderation'
                reason='you are in the experimental condition and this is second time you have visited'


    return render_template('base.html', color=color, page=page, reason=reason)