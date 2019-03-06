# Delete any existing database and relaunch the application
heroku pg:reset --confirm contentmoderationproject && heroku pg:psql -c "vacuum;" && heroku config:set WEB_CONCURRENCY=2 && heroku ps:restart web
