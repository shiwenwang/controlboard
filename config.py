import os
from datetime import timedelta
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:    
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'DO_NOT_USE_ON_PRODUCTION_ENVIRONMENT'
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOADS_DEFAULT_DEST = os.environ.get('CONTROLLER_REPOSITORY') or os.path.abspath(os.path.join(basedir, '../repository'))
    UPLOADED_BLADED_DEST = UPLOADS_DEFAULT_DEST
    UPLOADED_SYMBOL_DEST = UPLOADS_DEFAULT_DEST
    UPLOADED_XML_DEST = UPLOADS_DEFAULT_DEST
    UPLOADS_TEMPL_DEST = os.environ.get('CONTROLLER_DLL') or os.path.join(UPLOADS_DEFAULT_DEST, 'symbols')
    CALCULATION_DEST = os.path.abspath(os.path.join(basedir, '../calculation'))
    SEND_FILE_MAX_AGE_DEFAULT = timedelta(seconds=1)

    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True    
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,

    'default': DevelopmentConfig
}
