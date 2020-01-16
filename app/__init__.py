'''
@Descripttion: 
@version: 
@Author: wangshiwen@36719
@Date: 2019-10-02 14:35:27
@LastEditors  : wangshiwen@36719
@LastEditTime : 2020-01-14 09:00:40
'''
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_uploads import UploadSet, configure_uploads, patch_request_class
from config import config
from flask_wtf.csrf import CSRFProtect
from logging.config import dictConfig
import os, json, logging


csrf = CSRFProtect()
db = SQLAlchemy()
login_manager = LoginManager()
bladed = UploadSet('bladed', ('$pj', 'prj', '$PJ'))
# dll = UploadSet('dll', ('dll', ))
# xml = UploadSet('xml', ('xml', 'ini', 'txt'))
usets = (bladed,)


def create_app(config_name):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config[config_name])
    # config[config_name].init_app(app)
    # dictConfig(json.load(open(os.path.join(app.instance_path, 'logging.json'), 'r')))
    # dictConfig(yaml.load(open(os.path.join(app.instance_path, 'logging.conf')), Loader=yaml.FullLoader))

    csrf.init_app(app)
    db.init_app(app)
    migrate = Migrate(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    configure_uploads(app, (bladed, ))
    patch_request_class(app)

    from app.auth import auth
    app.register_blueprint(auth)

    from app.main import main
    app.register_blueprint(main)

    from app.task import task
    app.register_blueprint(task)

    return app
