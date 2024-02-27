import os
from flask import Flask, request, jsonify
from github import Github, GithubIntegration

app = Flask(__name__)

app_id = '825949'

# Read the bot certificate
with open(
        os.path.normpath(os.path.expanduser('bot_key.pem')),
        'r'
) as cert_file:
    app_key = cert_file.read()
    
# Create a GitHub integration instance
git_integration = GithubIntegration(
    app_id,
    app_key,
)

# Dictionary to store contributors' points
contributors_points = {}

# Set to keep track of displayed points for pull requests
displayed_points_for_pr = set()

# Set to keep track of responded comments
responded_comments = set()

# Function to handle pull request opened event
def pr_opened_event(repo, payload):
    pr = repo.get_issue(number=payload["pull_request"]["number"])
    author = pr.user.login

    # Increment the points of the contributor by 10 when they open a pull request
    contributors_points[author] = contributors_points.get(author, 0) + 10

    # Print out the points of each contributor
    points_message = "\n\nCurrent points:\n"
    for contributor, points in contributors_points.items():
        points_message += f"@{contributor}: {points}\n"

    is_first_pr = repo.get_issues(creator=author).totalCount

    if is_first_pr == True and pr.number not in displayed_points_for_pr:
        response = (
            f"Thanks for opening this pull request, @{author}! "
            f"The repository maintainers will look into it ASAP! :speech_balloon:"
            f"{points_message}"  # Include the points message in the response
        )
        pr.create_comment(f"{response}")
        pr.add_to_labels("needs review")
        displayed_points_for_pr.add(pr.number)

def pr_merged_event(repo, payload):
    pr_number = payload["pull_request"]["number"]
    branch_name = payload["pull_request"]["head"]["ref"]
    pr = repo.get_issue(number=pr_number)
    author = pr.user.login

    print("Pull Request merged event triggered.")
    print(f"PR Number: {pr_number}")
    print(f"Branch Name: {branch_name}")

    if payload["pull_request"]["merged"]:
        # Increment the points of the contributor by 50 when their pull request is merged
        contributors_points[author] = contributors_points.get(author, 0) + 50

        # Print out the points of each contributor
        points_message = "\n\nCurrent points:\n"
        for contributor, points in contributors_points.items():
            points_message += f"@{contributor}: {points}\n"

        response = (
            f"Your pull request has been successfully merged, @{author}. Thanks!"
            f"{points_message}"  # Include the points message in the response
        )
        pr.create_comment(f"{response}")
        pr.add_to_labels("accepted")

        # Delete the branch
        branch = repo.get_git_ref(f"heads/{branch_name}")
        print(f"Attempting to delete branch: {branch_name}")
        branch.delete()
        print(f"Branch {branch_name} deleted successfully.")

# Function to handle pull request prevent work-in-progress event
def pr_prevent_wip(repo, payload):
    pr = repo.get_issue(number=payload["pull_request"]["number"])
    author = pr.user.login
    sha = payload["pull_request"]["head"]["sha"]
    if (
        "wip" in payload["pull_request"]["title"].lower()
        or "work in progress" in payload["pull_request"]["title"].lower()
        or "do not merge" in payload["pull_request"]["title"].lower()
    ):
        repo.get_commit(sha=sha, state="pending")
        pr.add_to_labels("pending")
    pr.add_to_labels("success")

# Function to handle comment event
def comment_event(repo, payload):
    comment_body = payload["comment"]["body"]
    author = payload["comment"]["user"]["login"]
    commenter_is_bot = payload["comment"]["user"]["type"] == "Bot"

    # Check if the commenter is a bot, if so, return
    if commenter_is_bot:
        return

    # Check if "points" or "Points" is mentioned in the comment and the comment hasn't been responded to
    if "points" in comment_body.lower() and payload["comment"]["id"] not in responded_comments:
        points_message = "\n\nCurrent points:\n"
        for contributor, points in contributors_points.items():
            points_message += f"@{contributor}: {points}\n"

        response = f"@{author}, here are the current points:\n{points_message}"
        repo.get_issue(number=payload["issue"]["number"]).create_comment(response)
        responded_comments.add(payload["comment"]["id"])

    # Check if the commenter is a contributor and if the comment contains "delete" or "Delete"
    if author in contributors_points.keys() and ("delete" in comment_body.lower() or "delete" in comment_body.lower()):
        # Retrieve the pull request number and branch name
        pr_number = payload["issue"]["number"]
        branch_name = payload["issue"]["pull_request"]["head"]["ref"]
        repo.get_git_ref(f"heads/{branch_name}").delete()
        pr = repo.get_issue(number=pr_number)
        pr.create_comment("Branch deleted")
        pr.add_to_labels("deleted")

# Flask route to handle incoming GitHub webhook events
@app.route("/", methods=["POST"])
def bot():
    payload = request.json

    if not "repository" in payload.keys():
        return "", 204

    owner = payload["repository"]["owner"]["login"]
    repo_name = payload["repository"]["name"]

    git_connection = Github(
        login_or_token=git_integration.get_access_token(
            git_integration.get_installation(owner, repo_name).id
        ).token
    )
    repo = git_connection.get_repo(f"{owner}/{repo_name}")

    # Check if the event is a GitHub pull request creation event
    if (
        all(k in payload.keys() for k in ["action", "pull_request"])
        and payload["action"] == "opened"
    ):
        pr_opened_event(repo, payload)

    if (
        all(k in payload.keys() for k in ["action", "pull_request"])
        and payload["action"] == "closed"
    ):
        pr_merged_event(repo, payload)

    if (
        all(k in payload.keys() for k in ["action", "pull_request"])
        and payload["action"] == "edited"
    ):
        pr_prevent_wip(repo, payload)

    # Check if the event is a GitHub issue comment event
    if "comment" in payload.keys():
        comment_event(repo, payload)

    return "", 204

# Flask route to get contributors' points
@app.route("/points", methods=["GET"])
def get_contributors_points():
    return jsonify(contributors_points)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
