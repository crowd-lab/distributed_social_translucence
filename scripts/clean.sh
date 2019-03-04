# Delete any existing database and relaunch the application
heroku pg:reset --confirm jit-accountability && heroku pg:psql -c "vacuum;" && heroku ps:restart web
