import os


from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    indexes = db.execute("SELECT symbol, SUM(amount) FROM transactions GROUP BY symbol HAVING name = :name",
                         name=session["user_id"])
    total = 0

    # removes the rows that don't have a value anymore
    for row in indexes:
        if int(row["SUM(amount)"]) == 0:
            indexes.remove(row)

    # goes through all the lines that correspond to this id
    for i in range(len(indexes)):
        indexes[i]["price"] = lookup(indexes[i]["symbol"])["price"]
        indexes[i]["Fullname"] = lookup(indexes[i]["symbol"])["name"]
        indexes[i]["Curent"] = indexes[i]["price"]*indexes[i]["SUM(amount)"]
        total += indexes[i]["Curent"]

    cash = db.execute("Select cash FROM users WHERE id = :user_id", user_id=session["user_id"])

    cashe = cash[0]["cash"]
    b = {"symbol": "Cash", "Curent": cashe}
    indexes.append(b)
    total = total+cashe
    return render_template("index.html", indexes=indexes, total=total, cashe=cashe)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":

        # make sure there is a symbol
        if not request.form.get("symbol"):
            return apology("You need a symbol buddy", 400)

        # make sure there is a number of shares
        elif not request.form.get("shares"):
            return apology("you need an amount", 400)
        elif not lookup(request.form.get("symbol")):
            return apology("wrong stock symbol", 400)

        # the stock is then stocked in stock
        stock = lookup(request.form.get("symbol"))

        price = stock['price']
        price = int(price)
        result = request.form.get("shares").isdigit()

        if not result:
            return apology("shares must be an int", 400)

        shares = int(request.form.get("shares"))
        if shares <= 0:
            return apology("you need a positive amount", 400)

        # recuperates the cash available to the customer
        cash = db.execute("Select cash FROM users WHERE id = :user_id", user_id=session["user_id"])
        cashe = int(cash[0]["cash"])
        if cashe < (price * shares):
            return apology(" Sorry but you aint got enough money")
        else:
            # writes the transaction into the DB transaction
            db.execute("INSERT INTO transactions(name, symbol, amount, price, date) VALUES (:name, :symbol, :amount, :price, :date)",
                       name=session["user_id"], symbol=request.form.get("symbol"), amount=shares, price=price, date=datetime.now())

            # sets the remaining cash as it should be
            db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=(cashe-(price*shares)), user_id=session["user_id"])

            return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/changepw", methods=["GET", "POST"])
@login_required
def changepw():
    if request.method == "POST":
        if not request.form.get("password") or not request.form.get("newpw") or not request.form.get("confirmation"):
            return apology("you forgot something there")
        # check for current password correctness
        pw = db.execute("SELECT hash FROM users WHERE id = :username", username=session["user_id"])
        if not check_password_hash(pw[0]["hash"], request.form.get("password")):
            return apology("current password wrong")

        # check if the new password match
        if request.form.get("newpw") != request.form.get("confirmation"):
            return apology("both new password must match")

        # insert new password into the users db
        db.execute("UPDATE users SET hash =:hash WHERE id = :user_id",
                   hash=generate_password_hash(request.form.get("newpw")), user_id=session["user_id"])

        return redirect("/")
    else:
        return render_template("changepw.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    q = request.args.get("username")
    result = True
    username = db.execute("SELECT username FROM users")
    for i in range(len(username)):
        if q == username[i]["username"]:
            result = False
    return jsonify(result)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT symbol, amount, price, date  FROM transactions WHERE name = :name", name=session["user_id"])
    for i in range(len(history)):
        if int(history[i]["amount"]) < 0:
            history[i]["type"] = "Sale"
        else:
            history[i]["type"] = "Buy"

    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("wrong stock", 400)

        return render_template("quoted.html", stock=stock)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        # User entered username
        if not request.form.get("username"):
            return apology("Where is thy user name", 400)

        # User entered password
        elif not request.form.get("password") or not request.form.get("confirmation"):
            return apology("Where is thy passwor or confirmation")

        # Confirm password matches
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Can't you just copy paste", 400)

        registered = db.execute("INSERT INTO users(username, hash) VALUES (:username, :hash)",
                                username=request.form.get("username"), hash=generate_password_hash(request.form.get("password")))

        if not registered:
            return apology("username already exists", 400)

        return redirect("/login")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
     # """Sell shares of stock"""
    if request.method == "POST":
        if not request.form.get("shares") or not request.form.get("symbol") or (int(request.form.get("shares")) <= 0):
            return apology("Well that was not filled in properly")
        indexes = db.execute("SELECT SUM(amount) FROM transactions WHERE name = :name AND symbol = :symbol",
                             name=session["user_id"], symbol=request.form.get("symbol"))

    # removes the rows that don't have a value anymore
        for row in indexes:
            if int(row["SUM(amount)"]) < int(request.form.get("shares")):
                return apology("you don't have that many shares", 400)
        shares = (-1)*int(request.form.get("shares"))
        stock = lookup(request.form.get("symbol"))
        price = stock['price']

        # writes the transaction into the DB transaction
        db.execute("INSERT INTO transactions(name, symbol, amount, price, date) VALUES (:name, :symbol, :amount, :price, :date)",
                   name=session["user_id"], symbol=request.form.get("symbol"), amount=shares, price=price, date=datetime.now())
        cash = db.execute("Select cash FROM users WHERE id = :user_id", user_id=session["user_id"])
        cashe = int(cash[0]["cash"])
        db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=(cashe-(price*shares)), user_id=session["user_id"])

        return redirect("/")
    else:
        symbols = db.execute("SELECT symbol, SUM(amount) FROM transactions GROUP BY symbol HAVING name = :name",
                             name=session["user_id"])

    # removes the rows that don't have a value anymore
        for row in symbols:
            if int(row["SUM(amount)"]) == 0:
                symbols.remove(row)

        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
