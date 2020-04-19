import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

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

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # get list of stocks
    stocksdb = db.execute("SELECT symbol FROM purchases WHERE user_id=:userid GROUP BY symbol HAVING SUM(shares) > 0",
                        userid=session["user_id"])

    symbols = []

    for rows in stocksdb:
        symbols.append(rows.get("symbol").upper())

    # get list of stock names
    names = []

    for symbol in symbols:
        names.append(lookup(symbol).get("name"))

    # get list of number of shares
    shares = []

    for symbol in symbols:
        sharesdb = db.execute("SELECT SUM(shares) FROM purchases WHERE symbol=:symbol", symbol=symbol.lower())
        shares.append(sharesdb[0].get("SUM(shares)"))

    # get list market value
    market = []

    for symbol in symbols:
        market.append(lookup(symbol).get("price"))

    # get total list
    total = []
    counter = 0

    for symbol in symbols:
        total.append(round(float(shares[counter]) * market[counter], 2))
        counter += 1

    # get remainder
    remainder = 0
    remainderdb = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
    remainder = remainderdb[0].get("cash")

    # get bottom line (aka total of totals)
    bottomline = remainder

    for i in range(len(symbols)):
        bottomline += total[i]

    for i in range(len(total)):
        total[i] = usd(total[i])

    for i in range(len(market)):
        market[i] = usd(market[i])

    return render_template("index.html", symbols=symbols, names=names, shares=shares,
                            market=market, total=total, rows=len(symbols),
                            bottomline=usd(bottomline), remainder=usd(remainder))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        elif not request.form.get("shares"):
            return apology("number of shares invalid", 403)

        elif not lookup(request.form.get("symbol")):
            return apology("symbol invalid", 403)

        elif int(request.form.get("shares")) <= 0:
            return apology("number of shares invalid", 403)

        price = lookup(request.form.get("symbol")).get("price")

        userCash = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])

        shares = float(request.form.get("shares"))

        if shares * price > float(userCash[0].get("cash")):
            return apology("not enough cash", 403)

        # Buy: update purchases table and update users (cash) table
        db.execute("INSERT INTO purchases (user_id, symbol, shares, price, time) VALUES (:userid, :symbol, :shares, :price, CURRENT_TIMESTAMP)",
                    userid=session["user_id"], symbol=request.form.get("symbol").lower(), shares=int(shares), price=price)

        db.execute("UPDATE users SET cash=:remaining WHERE id=:id", remaining=(float(userCash[0].get("cash")) - shares * price), id=session["user_id"])

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    historydb = db.execute("SELECT symbol, shares, price, time FROM purchases WHERE user_id=:userid", userid=session["user_id"])

    return render_template("history.html", history=historydb)


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
    """Get stock quote."""
    if request.method == "POST":
        quoted = lookup(request.form.get("symbol"))
        return render_template("quoted.html", name=quoted.get("name"), price=quoted.get("price"),
        symbol=quoted.get("symbol"))

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
        # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure username does not already exist
        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))
        if len(rows) == 1:
            return apology("username already exists", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide password", 403)

        # Ensure confirmation = password
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match", 403)

        # Insert username into database
        db.execute("INSERT INTO users (username, hash, cash) VALUES (:username, :hash, 10000)",
                          username=request.form.get("username"),
                          hash=generate_password_hash(request.form.get("password")))

        # Redirect user to home page
        return redirect("/login")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        elif not request.form.get("shares"):
            return apology("number of shares invalid", 403)

        elif int(request.form.get("shares")) <= 0:
            return apology("number of shares invalid", 403)

        # check if user has enough stocks to sell
        sharesdb = db.execute("SELECT SUM(shares) FROM purchases WHERE symbol=:symbol", symbol=request.form.get("symbol").lower())
        sell = sharesdb[0].get("SUM(shares)")

        if int(request.form.get("shares")) > int(sharesdb[0].get("SUM(shares)")):
            return apology("number of shares invalid", 403)

        # Sell: update purchases table and update users (cash) table
        price = lookup(request.form.get("symbol")).get("price")

        userCash = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])

        db.execute("INSERT INTO purchases (user_id, symbol, shares, price, time) VALUES (:userid, :symbol, :shares, :price, CURRENT_TIMESTAMP)",
                    userid=session["user_id"], symbol=request.form.get("symbol").lower(), shares=-int(request.form.get("shares")), price=price)

        db.execute("UPDATE users SET cash=:remaining WHERE id=:id", remaining=(float(userCash[0].get("cash")) + float(request.form.get("shares")) * price), id=session["user_id"])

        return redirect("/")

    else:
        # get list of stock symbols
        stocksdb = db.execute("SELECT symbol FROM purchases WHERE user_id=:userid GROUP BY symbol",
                            userid=session["user_id"])
        symbols = []
        for rows in stocksdb:
            symbols.append(rows.get("symbol").upper())

        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
