from flask import Flask
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_uploads import UploadSet, configure_uploads, patch_request_class
from config import config


mail = Mail()
db = SQLAlchemy()
login_manager = LoginManager()
bladed = UploadSet('bladed', ('$PJ', '$PRJ', '$pj', '$prj'))
symbol = UploadSet('symbol', ('xls', 'xlsx'))
xml = UploadSet('xml', ('xml', 'ini', 'txt'))
usets = (bladed, symbol, xml)


def create_app(config_name):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    mail.init_app(app)
    db.init_app(app)
    migrate = Migrate(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    configure_uploads(app, (bladed, symbol, xml))
    patch_request_class(app)

    from app.auth import auth
    app.register_blueprint(auth)

    from app.main import main
    app.register_blueprint(main)

    from app.task import task
    app.register_blueprint(task)

    return app
