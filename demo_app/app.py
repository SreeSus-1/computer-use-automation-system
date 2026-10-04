from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse


app = FastAPI(title="Legacy Banking Demo")


# =========================================================
# DEMO MEMBER DATA
# =========================================================

MEMBERS = {
    "12345": {
        "name": "Demo Member",
        "balance": "$4,280.31",
    },

    # Used to demonstrate a recoverable/transient condition.
    "77777": {
        "name": "Retry Demo Member",
        "balance": "$7,777.77",
    },
}


# Tracks the transient-error demo.
#
# For member 77777:
#   first request  -> temporary error
#   second request -> success
#
# After success, the counter is reset so the scenario can
# be demonstrated again later.
TRANSIENT_ATTEMPTS: dict[str, int] = {}


# =========================================================
# SHARED HTML TEMPLATE
# =========================================================
#
# IMPORTANT:
# PAGE.format(body=body) is used throughout this file.
# Therefore CSS braces must be escaped as {{ and }}.
# =========================================================

PAGE = """
<!doctype html>

<html lang="en">

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>Legacy Banking Console</title>

    <style>

        body {{
            font-family: Arial, sans-serif;
            margin: 40px;
            background-color: #f5f5f5;
        }}

        table {{
            border-collapse: collapse;
            width: 100%;
        }}

        td {{
            padding: 8px;
        }}

        .panel {{
            border: 1px solid #999;
            padding: 20px;
            width: 520px;
            background-color: white;
        }}

        input {{
            padding: 8px;
            width: 220px;
        }}

        button {{
            padding: 8px 16px;
            cursor: pointer;
        }}

        .message {{
            margin-top: 15px;
        }}

        .error {{
            margin-top: 15px;
            font-weight: bold;
        }}

    </style>

</head>

<body>

    <div class="panel">

        <h1>Legacy Banking Console</h1>

        {body}

    </div>

</body>

</html>
"""


# =========================================================
# HOME / MEMBER SEARCH PAGE
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def home():

    body = """
    <form method="post" action="/search">

        <table>

            <tr>

                <td>
                    <label for="account_lookup">
                        Member ID
                    </label>
                </td>

                <td>
                    <input
                        id="account_lookup"
                        name="member_id"
                        type="text"
                        autocomplete="off"
                        required
                    >
                </td>

            </tr>

            <tr>

                <td colspan="2">

                    <button type="submit">
                        Search Member
                    </button>

                </td>

            </tr>

        </table>

    </form>
    """

    return PAGE.format(body=body)


# =========================================================
# MEMBER SEARCH
# =========================================================

@app.post("/search", response_class=HTMLResponse)
async def search(member_id: str = Form(...)):

    member_id = member_id.strip()


    # =====================================================
    # SCENARIO 1
    #
    # KNOWN BUSINESS OUTCOME
    # Member does not exist.
    # =====================================================

    if member_id == "99999":

        body = """
        <h2>Search Result</h2>

        <p class="message">
            No member found.
        </p>

        <a href="/">
            Back
        </a>
        """

        return PAGE.format(body=body)


    # =====================================================
    # SCENARIO 2
    #
    # PERMISSION DENIED
    # Human intervention is required.
    # =====================================================

    if member_id == "55555":

        body = """
        <h2>Permission Review</h2>

        <p class="message">
            Permission denied.
        </p>

        <p>
            A human operator must review this request.
        </p>

        <button
            type="button"
            onclick="
                document.getElementById('manual-review')
                .style.display='block';
            "
        >
            Manual Review
        </button>

        <div
            id="manual-review"
            style="display:none; margin-top:15px;"
        >

            <p>
                Operator action completed.
            </p>

            <a href="/">
                Return to search
            </a>

        </div>
        """

        return PAGE.format(body=body)


    # =====================================================
    # SCENARIO 3
    #
    # RECOVERABLE / TRANSIENT ERROR
    #
    # Member 77777 intentionally fails the first request.
    # The second request succeeds.
    # =====================================================

    if member_id == "77777":

        attempts = TRANSIENT_ATTEMPTS.get(
            member_id,
            0,
        )

        # -------------------------------------------------
        # FIRST ATTEMPT -> TRANSIENT FAILURE
        # -------------------------------------------------

        if attempts == 0:

            TRANSIENT_ATTEMPTS[member_id] = 1

            body = """
            <h2>Temporary Error</h2>

            <p class="error">
                Temporary system error.
            </p>

            <p>
                Please retry.
            </p>

            <a href="/">
                Retry Search
            </a>
            """

            return PAGE.format(body=body)

        # -------------------------------------------------
        # SECOND ATTEMPT -> ALLOW NORMAL SUCCESS
        # -------------------------------------------------

        # Reset the state so the transient scenario can
        # be demonstrated again on a future replay.
        TRANSIENT_ATTEMPTS[member_id] = 0


    # =====================================================
    # LOOK UP MEMBER
    # =====================================================

    member = MEMBERS.get(member_id)


    # =====================================================
    # UNKNOWN MEMBER
    #
    # Any ID not contained in MEMBERS is treated as a
    # legitimate business outcome rather than a crash.
    # =====================================================

    if member is None:

        body = """
        <h2>Search Result</h2>

        <p class="message">
            No member found.
        </p>

        <a href="/">
            Back
        </a>
        """

        return PAGE.format(body=body)


    # =====================================================
    # SUCCESSFUL MEMBER LOOKUP
    # =====================================================

    body = f"""
    <h2>Member Details</h2>

    <table>

        <tr>

            <td>
                Member ID
            </td>

            <td id="member_id">
                {member_id}
            </td>

        </tr>

        <tr>

            <td>
                Name
            </td>

            <td id="member_name">
                {member["name"]}
            </td>

        </tr>

        <tr>

            <td>
                Savings Balance
            </td>

            <td id="savings_balance">
                {member["balance"]}
            </td>

        </tr>

    </table>

    <br>

    <a href="/">
        Back
    </a>
    """

    return PAGE.format(body=body)