# Designate Flask application and launch on localhost
export FLASK_APP=accountability.py
export DATABASE_URL="postgres:///pairwise" #postgres://paul@localhost:5432/pairwise
python3 -m flask run --host=0.0.0.0