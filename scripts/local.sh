# Designate Flask application and launch on localhost
export FLASK_APP=accountability.py
export DATABASE_URL=$(heroku config:get DATABASE_URL)
python3 -m flask run
