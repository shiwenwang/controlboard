from flask import Blueprint, flash, render_template, redirect, url_for
from flask_login import current_user, login_user, logout_user, login_required
from app.forms import LoginForm, RegistrationForm, ConfirmForm, ResetPassWordForm, employees_query
from app.models import User, load_user
from app import db
import base64

auth = Blueprint('auth', __name__, url_prefix='/auth')


@auth.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.password = form.password.data
        user.realname = employees_query('姓名', OA=user.username)[0][0]
        user.role = employees_query('职位', OA=user.username)[0][0]
        db.session.add(user)
        db.session.commit()
        flash("注册成功！请登录。")
        return redirect(url_for('auth.login'))
    return render_template('register.html', form=form, title='注册')


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()        
        if user is None or not user.check_password(form.password.data):
            error_msg = '用户不存在。' if user is None else '密码错误。'
            flash(error_msg)
            return redirect(url_for('auth.login'))
        login_user(user, remember=form.remember.data)
        return redirect(url_for('main.index'))

    return render_template('login.html', form=form, title='登录')


@auth.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))


@auth.route('/reset', methods=['GET', 'POST'])
@login_required
def reset():
    form = ResetPassWordForm()
    next_state = "返回"
    if form.validate_on_submit():
        user_id = current_user.get_id()
        user = load_user(user_id)
        if user.check_password(form.old_password.data):
            user.password = form.new_password.data
            logout_user()
            next_state = "重新登录"
            flash("密码修改成功！")
        else:
            flash("密码错误！")
    return render_template('resetpw.html', form=form, next=next_state, title='修改密码')


@auth.route('/forgot',  methods=['GET', 'POST'])
def forgot():
    form = ConfirmForm()
    if form.validate_on_submit():
        real_name = User.query.filter_by(username=form.username.data).first().realname
        secure_name = base64.encodebytes(real_name.encode())
        return redirect(url_for('auth.cold_reset', name=secure_name))

    return render_template('forgot.html', form=form, title='忘记密码')


@auth.route('/cold-reset/<name>', methods=['GET', 'POST'])
def cold_reset(name):
    form = ResetPassWordForm()
    next_state = "返回"
    if form.validate_on_submit():
        user = User.query.filter_by(realname=base64.decodebytes(name.encode()).decode()).first()
        if user.check_password(form.old_password.data):
            user.password = form.new_password.data
            logout_user()
            next_state = "登录"
            flash("密码修改成功！")
        else:
            flash("密码错误！")
    return render_template('resetpw.html', form=form, next=next_state, title='修改密码')
