# Designate Flask application and launch so it's visible outside localhost
export FLASK_APP=accountability.py
python -m flask run --host=0.0.0.0
