# Delete any existing database and relaunch the application
heroku pg:reset --confirm jit-accountability && heroku pg:psql -c "vacuum;" && heroku config:set WEB_CONCURRENCY=1 && heroku ps:restart web
