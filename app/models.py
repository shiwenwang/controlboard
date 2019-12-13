from app import db, login_manager
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from flask import url_for


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(24), unique=True)
    realname = db.Column(db.String(24))
    email = db.Column(db.String(120), unique=True)
    role = db.Column(db.String(120))
    _password = db.Column('password', db.String(128))

    tasks = db.relationship('Task', backref='creator', lazy='dynamic')

    @property
    def password(self):
        return self._password

    @password.setter
    def password(self, plain_password):
        hash_password = generate_password_hash(plain_password)
        self._password = hash_password

    def check_password(self, plain_password):
        return check_password_hash(self._password, plain_password)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256), unique=True)
    status = db.Column(db.String(24))
    date_stamp = db.Column(db.DateTime, index=True, default=datetime.now)
    bladed_version = db.Column(db.String(8))
    isgitted = db.Column(db.Integer)

    user = db.relationship('User')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    bladed_filename = db.Column(db.String(128))
    bladed_url = db.Column(db.String(256))
    xml_filename = db.Column(db.String(128))
    xml_url = db.Column(db.String(256))
    symbol_index = db.Column(db.Integer)
    symbol_filename = db.Column(db.String(128))
    symbol_url = db.Column(db.String(256))

    tower_mode_1 = db.Column(db.Float)

    @staticmethod
    def date_str(datestamp):
        return datestamp.strftime('%Y-%m-%d %H:%M:%S')

    def to_json(self, show_id):
        status_map = {"New": ("secondary", "尚未修改"),
                      "Saved": ("success", "文件已保存"),
                      "Dirty": ("warning", "文件已保存，修改未提交"),
                      "Clean": ("success", "文件已保存，修改已提交")}
        return {'id': show_id,
                'name': f'<a id="task" href="{url_for("task.work", taskname=self.name)}" target="_blank">{self.name}</a>',
                # 'name': f"<a href=\"javascript: openTask('{self.name}')\">{self.name}</a>",
                'date': self.date_str(self.date_stamp),
                'status': f'<h6 style="margin-bottom:0;"><span class="badge badge-{status_map[self.status][0]}" data-toggle="tooltip" title="'
                f'{status_map[self.status][1]}"><i class="fas fa-code-branch"></i> {self.status}</span></h6>' if self.isgitted else
                f'<h6 style="margin-bottom:0;"><span class="badge badge-{status_map[self.status][0]}" data-toggle="tooltip" title="'
                f'{status_map[self.status][1]}">{self.status}</span></h6>',
                'bladed_version': self.bladed_version,
                'creator': self.user.realname,
                'operate': '''
                            <div class="d-sm-flex flex-row justify-content-center">
                                <div class="p-1">
                                    <h6 style="margin-bottom:0;">
                                        <span id="edit-badge" class="badge badge-primary" data-events="editEvents" style="cursor: pointer">
                                            <i class="fas fa-edit"></i>
                                        </span>
                                    </h6>
                                </div>                                
                                <div class="p-1">
                                    <h6 style="margin-bottom:0;">
                                        <span id="delete-badge" class="badge badge-danger" data-events="deleteEvents" " data-toggle="modal"
                                            data-target="#DeleteTaskModal" style="cursor: pointer">
                                            <i class="fas fa-trash-alt"></i>
                                        </span>
                                    </h6>
                                </div>
                            </div>
                            '''
                }


@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))
