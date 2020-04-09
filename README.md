# PairWise Installation

Installing PairWise is fairly straightforward, since it's a pretty stock [Flask](https://flask.palletsprojects.com/en/1.1.x/) app. It basically entails the following steps:

## Setup Postgres
You will need a `postgresql` installation, anything after Postgres11 should be fine. Once you have that setup, you may want to configure a user (`postgres` is often the default user, which is fine as well).

Once you have this setup, use the `createdb` command to create the database you want PairWise to interact with. For instance: `createdb pairwise_data`.

You will need to know your:
- postgres username (`USERNAME` below)
- postgres password (`PASSWORD` below, often left blank for local installations)
- the name of the database you created above (`DATABASE_NAME` below, e.g. `pairwise_data`)

### Setup the necessary environment variables
#### Setup `DATABASE_URL`
On the command line, run the command:
`export DATABASE_URL=postgres://USERNAME:PASSWORD@localhost:5432/DATABASE_NAME`

For instance, using the defaults described above, this might be
`export DATABASE_URL=postgres://postgres@localhost:5432/pairwise_data`

#### Setup `FLASK_APP`
To point Flask to right `.py` file, you will also need to run
`export FLASK_APP=accountability.py`

## Setup Python
Once you have a database setup, you will then need to setup a `python3` environment. You can choose to use `virtualenv` if you would like 

If you are using a `virtualenv`, make sure you have activated it.

### Installing necessary libraries
To install the necessary libraries, within the root folder for PairWise `distributed_social_accountability` by default, run:
`pip install -r ./requirements.txt`

# Run PairWise
To run PairWise, once you have configured everything above correctly, you should be able to just run
`flask run`

Which will start the flask server on `http://locahost:5000`. 

# Testing PairWise
Because PairWise runs as an app for Mechanical Turk, the starting page to interact with PairWise is `http://localhost:5000/narrative?workerId=[YOUR WORKER ID HERE]`.

*NOTE*: You *must* use Chrome, currently, to test and use PairWise. We enforce this in order to ensure a common experience for Mechanical Turk workers. 
