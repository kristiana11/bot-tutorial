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
    
# Create an GitHub integration instance
git_integration = GithubIntegration(
    app_id,
    app_key,
)

# Dictionary to store contributors' points
contributors_points = {}

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

    if is_first_pr == True:
        response = (
            f"Thanks for opening this pull request, @{author}! "
            f"The repository maintainers will look into it ASAP! :speech_balloon:"
            f"{points_message}"  # Include the points message in the response
        )
        pr.create_comment(f"{response}")
        pr.add_to_labels("needs review")


def pr_merged_event(repo, payload):
    pr = repo.get_issue(number=payload["pull_request"]["number"])
    author = pr.user.login

    if payload["pull_request"]["merged"]:
        # Increment the points of the contributor by 50 when their pull request is merged
        contributors_points[author] = contributors_points.get(author, 0) + 50

        # Print out the points of each contributor
        points_message = "\n\nCurrent points:\n"
        for contributor, points in contributors_points.items():
            points_message += f"@{contributor}: {points}\n"

        response = (
            f"Your pull request has been successfully merged, @{author}. Thanks !"
            f"{points_message}"  # Include the points message in the response
        )
    pr.create_comment(f"{response}")
    pr.add_to_labels("accepted")


def pr_delete_merged_branch(repo, payload):
    pr = repo.get_issue(number=payload["pull_request"]["number"])
    author = pr.user.login
    if payload["pull_request"]["merged"]:
        branch_name = payload["pull_request"]["head"]["ref"]
        repo.get_git_ref(f"heads/{branch_name}").delete()
    pr.create_comment("Branch deleted")
    pr.add_to_labels("deleted")


def pr_prevent_wip(repo, payload):
    pr = repo.get_issue(number=payload["pull_request"]["number"])
    author = pr.user.login
    sha = payload["pull_request"]["head"]["sha"]
    if (
        payload["pull_request"]["title"].contains("wip")
        or payload["pull_request"]["title"].contains("work in progress")
        or payload["pull_request"]["title"].contains("do not merge")
    ):
        repo.get_commit(sha=sha, state="pending")
        pr.add_to_labels("pending")
    pr.add_to_labels("success")


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
        pr_delete_merged_branch(repo, payload)

    if (
        all(k in payload.keys() for k in ["action", "pull_request"])
        and payload["action"] == "edited"
    ):
        pr_prevent_wip(repo, payload)

    return "", 204


@app.route("/points", methods=["GET"])
def get_contributors_points():
    return jsonify(contributors_points)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
