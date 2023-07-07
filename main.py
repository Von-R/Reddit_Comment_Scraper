import praw
import pandas as pd
import json
import os
import glob
import re
from textblob import TextBlob
import spacy

SIMILARITY_THRESHOLD = 0.3  # Similarity threshold for filtering comments

nlp = spacy.load('en_core_web_md')  # Load spaCy's medium English model

reddit = praw.Reddit(
    client_id="vzqeHlhnmUQGls_0iqTUkQ",
    client_secret="9JqnyUVYba2QcTR-dqMzzqJJQS4p6A",
    password="Iwanttobehappy!99!",
    user_agent="script: CommentBot by _Stahl",
    username="_Stahl"
)

subreddits = []


def analyze_sentiment(comment):
    blob = TextBlob(comment)
    sentiment = blob.sentiment.polarity  # Get sentiment polarity
    return sentiment


def filter_comments(title, comments):
    filtered_comments = []
    removed_comments = []

    title_doc = nlp(title)

    for comment in comments:
        comment_doc = nlp(comment)

        # Ignore empty comments and those with a similarity score < 0.3
        if comment_doc.vector_norm and title_doc.vector_norm and comment_doc.similarity(title_doc) >= SIMILARITY_THRESHOLD:
            filtered_comments.append(comment)
        else:
            removed_comments.append(comment)

    return filtered_comments, removed_comments


def clean_text(text):
    """
    Function to clean text by removing or replacing certain problematic strings.
    """
    # Remove unicode escape sequences
    text = re.sub(r'(\\u[0-9A-Fa-f]+)', '', text)
    text = re.sub(r'(\\n)', '', text)
    text = re.sub(r'(\\r)', '', text)
    text = re.sub(r'(\\t)', '', text)
    text = re.sub(r'(\\b)', '', text)
    text = re.sub(r'(\\f)', '', text)
    text = text.lower()

    return text


def compile_json():
    main_json = {}  # Main JSON object to be written to a file

    for subreddit in subreddits:
        subreddit_json = {}  # JSON object for the subreddit

        # Get all CSV files for the subreddit
        csv_files = glob.glob(f'{subreddit}_top_comments_post_*.csv')

        for i, csv_file in enumerate(csv_files):
            df = pd.read_csv(csv_file)  # Load CSV file into DataFrame

            post_title = df.iloc[0]['post_title']  # Get post title
            top_comments = df['comment'].tolist()  # Get list of top comments

            # Filter comments
            filtered_comments = filter_comments(post_title, top_comments)
            # Perform sentiment analysis on filtered comments
            sentiments = [analyze_sentiment(comment) for comment in filtered_comments]
            # Calculate average sentiment
            average_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0

            # Create post dictionary and add it to the subreddit JSON object
            post_dict = {
                'title': post_title,
                'top_comments': filtered_comments,
                'sentiment': average_sentiment
            }
            subreddit_json[f'Post_{i + 1}'] = post_dict

        # Add subreddit JSON object to the main JSON object
        main_json[f'Subreddit_title: {subreddit}'] = subreddit_json

    # Write main JSON object to a file
    with open('compiled.json', 'w') as file:
        json.dump(main_json, file, indent=4)


def load_subreddits():
    try:
        with open('subreddits.json', 'r') as file:
            subreddits.extend(json.load(file))
    except FileNotFoundError:
        print("File not found. Will create a new one when adding subreddits.")


def add_subreddit():
    while True:
        subreddit_name = input("Enter the subreddit to add (type '1' to finish): ")
        if subreddit_name == '1':
            break
        subreddits.append(subreddit_name)
    with open('subreddits.json', 'w') as file:
        json.dump(subreddits, file)


def remove_subreddit():
    subreddit_name = input("Enter the subreddit to remove: ")
    if subreddit_name in subreddits:
        subreddits.remove(subreddit_name)
        with open('subreddits.json', 'w') as file:
            json.dump(subreddits, file)


def delete_list():
    subreddits.clear()
    with open('subreddits.json', 'w') as file:
        json.dump(subreddits, file)


def delete_csv_files():
    files = glob.glob('*.csv')
    for file in files:
        os.remove(file)


def display_subreddits():
    print("\n".join(subreddits))


def get_top_posts(subreddits, num_posts, num_comments):
    #reddit = praw.Reddit(client_id='my_client_id', client_secret='my_client_secret', user_agent='my_user_agent')

    for subreddit_title in subreddits:
        subreddit = reddit.subreddit(subreddit_title)
        top_posts = subreddit.top(limit=num_posts)

        filtered_data = {"Subreddit_title": subreddit_title, "Posts": []}

        for post in top_posts:
            top_comments = [comment.body for comment in list(post.comments)[:num_comments]]

            filtered_comments, removed_comments = filter_comments(post.title, top_comments)

            # Only append the post if it has at least one valid comment
            if filtered_comments:
                filtered_data["Posts"].append({
                    "title": post.title,
                    "top_comments": filtered_comments
                })

            with open(f'removed_{subreddit_title}.json', 'w') as removed_file:
                json.dump({"Subreddit_title": subreddit_title, "Removed_Comments": removed_comments}, removed_file)

        # Only write the file if it contains at least one post with valid comments
        if filtered_data["Posts"]:
            with open(f'filtered_{subreddit_title}.json', 'w') as json_file:
                json.dump(filtered_data, json_file)


def contains_term(string, terms):
    for term in terms:
        if term.lower() in string.lower():  # Convert both to lower case to make the check case-insensitive
            return True
    return False


def get_top_comments(post, n, min_votes):
    """
    Function to get top n comments from a post
    """
    post.comments.replace_more(limit=None)
    comments = post.comments.list()

    # Define the list of terms you want to omit
    omit_terms = ["http://", "https://", "OF", "insta", "pornhub", "removed", "deleted", "r/", "r /"]

    sorted_comments = []

    for comment in sorted(comments, key=lambda comment: comment.score, reverse=True):
        # Check if the comment score is greater than min_votes, the commenter's username is different from post's author
        # and the comment doesn't contain any term from the omit_terms list
        if comment.score >= min_votes and comment.author != post.author and not contains_term(comment.body, omit_terms):
            # Clean the comment before adding it
            cleaned_comment = clean_text(comment.body)
            sorted_comments.append(cleaned_comment)

    return sorted_comments[:n]


def store_comments(comments, post_title, filename):
    """
    Function to store comments in a csv file
    """
    data = []
    print("Storing comments...")
    for comment in comments:
        data.append([comment.author, comment.body, comment.score, post_title])

    df = pd.DataFrame(data, columns=['author', 'comment', 'score', 'post_title'])
    df.to_csv(filename, index=False)
    print("Comments stored!")


def delete_json_files():
    files = glob.glob('*.json')
    for file in files:
        os.remove(file)


def combine_json_files(output_file_name):
    # Get the current working directory
    directory = os.getcwd()

    # This line is changed to search for only files that start with 'filtered'
    json_files = glob.glob(os.path.join(directory, '*_filtered_*.json'))

    data = {}

    for json_file in json_files:
        with open(json_file, 'r') as file:
            file_data = json.load(file)

        # Merge file_data into data
        data.update(file_data)

    # Write combined data to output file
    with open(os.path.join(directory, output_file_name), 'w') as output_file:
        json.dump(data, output_file)


def main():
    load_subreddits()

    while True:
        print("\nOptions:")
        print("Set Up:")
        print("1. Add subreddit")
        print("2. Remove subreddit")
        print("3. Display subreddits")
        print("4. Delete all subreddits from the list")
        print("5. Delete all JSON files")
        print("Collection:")
        print("6. Fetch data")
        print("7. Combine JSON files")
        print("Processing:")
        print("8. Process sentiment analysis")
        print("9. Quit")

        try:
            option = int(input("Choose an option: "))
        except ValueError:
            print("Invalid input. Please enter a number corresponding to an option.")
            continue

        if option == 1:
            add_subreddit()
        elif option == 2:
            remove_subreddit()
        elif option == 3:
            display_subreddits()
        elif option == 4:
            delete_list()
        elif option == 5:
            delete_json_files()
        elif option == 6:
            n_posts = input("Enter the number of posts (default is 10): ")
            n_comments = input("Enter the number of comments per post (default is 10): ")

            n_posts = 10 if n_posts == "" else int(n_posts)
            n_comments = 10 if n_comments == "" else int(n_comments)

            get_top_posts(subreddits, n_posts, n_comments)  # Corrected function call

        elif option == 7:
            combine_json_files('combined_filtered.json')
        elif option == 8:
            break


if __name__ == '__main__':
    main()
