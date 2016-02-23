from nautilus.flask_ext import FlaskNautilus
from werkzeug.contrib.cache import FileSystemCache, RedisCache
from flask import Flask
from flask_cache import Cache

nautilus_cache = RedisCache()
app = Flask("Nautilus")
nautilus = FlaskNautilus(
    app=app,
    resources=["/home/thibault/dev/canonicals/canonical-latinLit"],
    parser_cache=nautilus_cache,
    http_cache=Cache(config={'CACHE_TYPE': 'redis'})
)
app.run(debug=True)#, host='192.168.1.177')
