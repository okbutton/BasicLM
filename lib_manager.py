import sys
import sqlite3
import os
import requests
import datetime
from datetime import timedelta

# Register adapters and converters for date and datetime handling
sqlite3.register_adapter(datetime.date, lambda d: d.isoformat())
sqlite3.register_converter('DATE', lambda s: datetime.date.fromisoformat(s.decode('utf-8')))
sqlite3.register_adapter(datetime.datetime, lambda dt: dt.isoformat(sep=' '))
sqlite3.register_converter('DATETIME', lambda s: datetime.datetime.fromisoformat(s.decode('utf-8')))

# Connect to SQLite database
conn = sqlite3.connect('library.db', detect_types=sqlite3.PARSE_DECLTYPES)
cursor = conn.cursor()

# Create tables
cursor.execute('''
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    authors TEXT,
    publisher TEXT,
    published_date TEXT,
    isbn TEXT UNIQUE,
    page_count INTEGER,
    description TEXT,
    language TEXT,
    category TEXT,
    copies_available INTEGER DEFAULT 1,
    tree_level_id INTEGER REFERENCES tree_levels(id),
    reference_only BOOLEAN DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS tree_levels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS borrowers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id TEXT UNIQUE
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER,
    borrower_id INTEGER,
    borrow_date DATE,
    return_date DATE,
    FOREIGN KEY(book_id) REFERENCES books(id),
    FOREIGN KEY(borrower_id) REFERENCES borrowers(id)
)
''')

conn.commit()

#Function to set a book to be referance only
def set_reference_only():
    clear_screen()
    isbn = input("Enter the ISBN of the book to update: ")

    # Fetch book details based on the ISBN
    cursor.execute("SELECT id, title, reference_only FROM books WHERE isbn = ?", (isbn,))
    book = cursor.fetchone()

    if book:
        book_id, title, reference_only = book

        # Display the current reference status
        print(f"Book Title: {title}")
        print(f"Current Reference Only Status: {'Yes' if reference_only else 'No'}")

        # Ask the user to set the new reference status
        new_reference_only = input("Do you want to set this book as reference only (y/n)? ").lower() == 'y'

        # Update the book's reference status in the database
        cursor.execute("UPDATE books SET reference_only = ? WHERE id = ?", (new_reference_only, book_id))
        conn.commit()

        print(f"\nReference status for '{title}' has been updated to: {'Yes' if new_reference_only else 'No'}")
    else:
        print(f"No book found with ISBN: {isbn}")

    input("\nPress Enter to return to the menu...")

#Function to view borower details
def view_borrower_details():
    clear_screen()
    card_id = input("Enter the borrower's card ID: ")

    # Fetch borrower details
    cursor.execute("SELECT id, card_id FROM borrowers WHERE card_id = ?", (card_id,))
    borrower = cursor.fetchone()

    if borrower:
        borrower_id, borrower_card_id = borrower

        # Display borrower information
        print(f"Borrower Details:\nCard ID: {borrower_card_id}\n")

        # Fetch books currently borrowed by the borrower
        sql = '''
        SELECT books.title, books.isbn, loans.borrow_date, loans.return_date
        FROM loans
        INNER JOIN books ON loans.book_id = books.id
        WHERE loans.borrower_id = ? AND loans.return_date IS NULL
        '''
        cursor.execute(sql, (borrower_id,))
        borrowed_books = cursor.fetchall()

        if borrowed_books:
            print("Currently Borrowed Books:")
            for book in borrowed_books:
                title, isbn, loan_date, return_date = book
                due_date = datetime.datetime.strptime(loan_date, '%Y-%m-%d').date() + timedelta(weeks=2)
                print(f"Title: {title}")
                print(f"ISBN: {isbn}")
                print(f"Loan Date: {loan_date}")
                print(f"Due Date: {due_date}")
                print("-" * 40)
        else:
            print("No books currently borrowed by this borrower.")

    else:
        print(f"No borrower found with card ID: {card_id}")
    
    input("\nPress Enter to return to the menu...")

#Function to asign a book to a tree level
def assign_tree_level_to_book():
    clear_screen()
    isbn = input("Enter the ISBN of the book to assign a tree level: ")

    # Fetch the book details based on the ISBN
    cursor.execute("SELECT id, title FROM books WHERE isbn = ?", (isbn,))
    book = cursor.fetchone()

    if book:
        print(f"Book found: {book[1]} (ISBN: {isbn})")

        # Display the available tree levels
        cursor.execute("SELECT id, name FROM tree_levels")
        tree_levels = cursor.fetchall()

        if tree_levels:
            print("\nAvailable Tree Levels:")
            for level in tree_levels:
                print(f"{level[0]}. {level[1]}")
            
            # Ask user to select a tree level
            level_choice = input("\nEnter the ID of the tree level to assign to the book: ")

            # Assign the selected tree level to the book
            cursor.execute("UPDATE books SET tree_level_id = ? WHERE isbn = ?", (level_choice, isbn))
            conn.commit()

            print(f"Tree level '{level_choice}' assigned to the book '{book[1]}'")
        else:
            print("No tree levels available. Add some categories first.")
    else:
        print(f"No book found with ISBN: {isbn}")

    input("\nPress Enter to return to the menu...")

# Function to add a tree level
def add_tree_level():
    clear_screen()
    tree_level = input("Enter a new tree level: ")
    
    try:
        cursor.execute("INSERT INTO tree_levels (name) VALUES (?)", (tree_level,))
        conn.commit()
        print(f"Tree level '{tree_level}' added successfully.")
    except sqlite3.IntegrityError:
        print(f"Tree level '{tree_level}' already exists.")
    
    input("\nPress Enter to return to the menu...")

# Function to clear the screen
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# Function to fetch book data from Google Books API and return the preferred ISBN
def fetch_book_data(isbn):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if "items" in data:
            book_data = data["items"][0]["volumeInfo"]
            
            # Retrieve the ISBN-13 or ISBN-10 from the book data
            isbn_list = book_data.get('industryIdentifiers', [])
            isbn_13 = next((x['identifier'] for x in isbn_list if x['type'] == 'ISBN_13'), None)
            isbn_10 = next((x['identifier'] for x in isbn_list if x['type'] == 'ISBN_10'), None)
            # Prefer ISBN-13, but fall back to ISBN-10 if necessary
            book_isbn = isbn_13 if isbn_13 else isbn_10
            
            return book_data, book_isbn
        else:
            return None, None
    return None, None

# Function to insert book data into the SQLite database
def insert_book_data(book_data, retrieved_isbn):
    sql = '''
    INSERT INTO books (title, authors, publisher, published_date, isbn, page_count, description, language, category, copies_available)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    '''
    cursor.execute(sql, (
        book_data.get('title'),
        ', '.join(book_data.get('authors', [])),
        book_data.get('publisher'),
        book_data.get('publishedDate'),
        retrieved_isbn,
        book_data.get('pageCount'),
        book_data.get('description'),
        book_data.get('language'),
        ', '.join(book_data.get('categories', []))
    ))
    conn.commit()

# Function to display book data
def display_book_data(book_data):
    print("\nBook Details:")
    print(f"Title: {book_data.get('title')}")
    print(f"Authors: {', '.join(book_data.get('authors', []))}")
    print(f"Publisher: {book_data.get('publisher')}")
    print(f"Published Date: {book_data.get('publishedDate')}")
    print(f"Page Count: {book_data.get('pageCount')}")
    print(f"Description: {book_data.get('description')}")
    print(f"Language: {book_data.get('language')}")
    print(f"Categories: {', '.join(book_data.get('categories', []))}")

# Function to add a book to the inventory with duplicate check and confirmation using API's ISBN
def add_book_to_inventory():
    while True:
        isbn_input = input("\nEnter the ISBN of the book (leave empty to quit): ")
        
        if not isbn_input:  # Quit if no ISBN is entered
            print("Exiting book addition process.")
            break
        
        # Fetch and show book details for confirmation
        book_data, retrieved_isbn = fetch_book_data(isbn_input)
        
        if book_data and retrieved_isbn:
            # Check if the book with the retrieved ISBN already exists
            cursor.execute('SELECT * FROM books WHERE isbn = ?', (retrieved_isbn,))
            book = cursor.fetchone()

            if book:
                # If the book exists, increment the available copies
                print(f"Book with ISBN {retrieved_isbn} already exists. Adding another copy.")
                cursor.execute('UPDATE books SET copies_available = copies_available + 1 WHERE isbn = ?', (retrieved_isbn,))
                conn.commit()
                print(f"Copies available updated. Now {book[-1] + 1} copies available.")
            else:
                # Display book data and confirm addition
                display_book_data(book_data)
                confirm = input("\nDo you want to add this book to the inventory? (y/n): ")
                if confirm.lower() == 'y':
                    # Insert the book into the database
                    insert_book_data(book_data, retrieved_isbn)
                    print(f"\nBook '{book_data['title']}' added to inventory with 1 copy.")
                else:
                    print("Book addition canceled.")
        else:
            print("Book not found in Google Books API or no valid ISBN found.")

# Function to list all books in the inventory (with tree level)
def list_all_books():
    clear_screen()
    cursor.execute('''
    SELECT books.title, books.authors, books.isbn, books.published_date, books.copies_available, tree_levels.name
    FROM books
    LEFT JOIN tree_levels ON books.tree_level_id = tree_levels.id
    ''')
    results = cursor.fetchall()

    if results:
        print("\nList of all books:")
        for row in results:
            print(f"Title: {row[0]}, Authors: {row[1]}, ISBN: {row[2]}, Published: {row[3]}, Copies Available: {row[4]}, Tree Level: {row[5] or 'Not assigned'}")
    else:
        print("No books available in the inventory.")
    
    input("\nPress Enter to return to the menu...")

# Function to search for a book by title, author, or ISBN
def search_books():
    clear_screen()
    search_term = input("Enter a title, author, or ISBN to search: ")

    sql = '''
    SELECT books.title, books.authors, books.isbn, books.published_date, books.copies_available, books.reference_only, tree_levels.name, 
           borrowers.card_id, loans.return_date
    FROM books
    LEFT JOIN tree_levels ON books.tree_level_id = tree_levels.id
    LEFT JOIN loans ON books.id = loans.book_id
    LEFT JOIN borrowers ON loans.borrower_id = borrowers.id
    WHERE books.title LIKE ? OR books.authors LIKE ? OR books.isbn = ?
    '''
    
    cursor.execute(sql, (f'%{search_term}%', f'%{search_term}%', search_term))
    results = cursor.fetchall()

    if results:
        print("\nSearch Results:")
        for row in results:
            title, authors, isbn, published_date, copies_available, reference_only, tree_level, borrower_id, return_date = row
            
            # Display book details
            print(f"Title: {title}")
            print(f"Authors: {authors}")
            print(f"ISBN: {isbn}")
            print(f"Published: {published_date}")
            print(f"Copies Available: {copies_available}")
            print(f"Reference Only: {'Yes' if reference_only else 'No'}")
            print(f"Tree Level: {tree_level if tree_level else 'Not assigned'}")

            # Display borrower details if the book is borrowed
            if borrower_id:
                print(f"Borrower ID: {borrower_id}")
                print(f"Due Date: {return_date}")
            else:
                print("Currently not borrowed.")
            
            print("-" * 40)
    else:
        print("No books found matching the search term.")

    input("\nPress Enter to return to the menu...")

# Function to add a borrower
def add_borrower():
    card_id = input("Enter the borrower's library card ID: ")

    try:
        cursor.execute('INSERT INTO borrowers (card_id) VALUES (?)', (card_id,))
        conn.commit()
        print(f"Borrower '{card_id}' added successfully.")
        input("\nPress Enter to return to the menu...")
    except sqlite3.IntegrityError:
        print(f"Borrower with ID '{card_id}' already exists.")
        input("\nPress Enter to return to the menu...")

# Function to check out a book
def check_out_book():
    clear_screen()
    isbn = input("Enter the ISBN of the book to check out: ")

    # Check if the book is in the database and if it's for reference only
    cursor.execute("SELECT id, title, copies_available, reference_only FROM books WHERE isbn = ?", (isbn,))
    book = cursor.fetchone()

    if book:
        book_id, title, copies_available, reference_only = book

        if reference_only:
            print(f"The book '{title}' is for reference only and cannot be checked out.")
        elif copies_available > 0:
            borrower_id = input("Enter the borrower's card ID: ")
            cursor.execute("SELECT id FROM borrowers WHERE card_id = ?", (borrower_id,))
            borrower = cursor.fetchone()

            if borrower:
                borrower_id = borrower[0]
                cursor.execute("INSERT INTO loans (book_id, borrower_id, loan_date) VALUES (?, ?, ?)", (book_id, borrower_id, datetime.now()))
                cursor.execute("UPDATE books SET copies_available = copies_available - 1 WHERE id = ?", (book_id,))
                conn.commit()
                print(f"Book '{title}' checked out successfully.")
            else:
                print(f"No borrower found with card ID: {borrower_id}")
        else:
            print(f"No available copies of '{title}' to check out.")
    else:
        print(f"No book found with ISBN: {isbn}")

    input("\nPress Enter to return to the menu...")

# Function to check in a book
def check_in_book():
    isbn = input("Enter the ISBN of the book being returned: ")

    cursor.execute('SELECT id FROM books WHERE isbn = ?', (isbn,))
    book = cursor.fetchone()

    if book:
        cursor.execute('DELETE FROM loans WHERE book_id = ? ORDER BY borrow_date DESC LIMIT 1', (book[0],))
        conn.commit()

        # Increase copies available
        cursor.execute('UPDATE books SET copies_available = copies_available + 1 WHERE id = ?', (book[0],))
        conn.commit()

        print(f"Book with ISBN {isbn} checked in.")
    else:
        print("Book not found.")
    
    input("\nPress Enter to return to the menu...")

# Function to list all late books
def list_late_books():
    clear_screen()
    today = datetime.date.today()
    cursor.execute('''
    SELECT books.title, borrowers.card_id, loans.return_date 
    FROM loans
    JOIN books ON loans.book_id = books.id
    JOIN borrowers ON loans.borrower_id = borrowers.id
    WHERE loans.return_date < ?
    ''', (today,))
    results = cursor.fetchall()

    if results:
        print("\nLate Books:")
        for row in results:
            print(f"Title: {row[0]}, Borrower: {row[1]}, Due: {row[2]}")
    else:
        print("No late books.")

    input("\nPress Enter to return to the menu...")

# Management Menu
def man_menu():
    while True:
        clear_screen()
        print("Library Management System")
        print("1. Add books")
        print("2. Add a borrower")
        print("3. Add a Reading Tree Branch")
        print("4. Assign a book to a Branch")
        print("5. Mark a book as Reference")
        print("6. View a borrower")
        print("0. Main Menu")

        choice = input("\nEnter your choice: ")

        if choice == '1':
            add_book_to_inventory()
        elif choice == '2':
            add_borrower()
        elif choice == '3':
            add_tree_level()
        elif choice == '4':
            assign_tree_level_to_book()
        elif choice == '5':
            set_reference_only()
        elif choice == '6':
            view_borrower_details()
        elif choice == '0':
            main_menu()
        else:
            input("\nInvalid choice, Press Enter to try again.")

# Main menu
def main_menu():
    while True:
        clear_screen()
        print("Library Management System")
        print("1. Check out a book")
        print("2. Check in a book")
        print("3. List late books")
        print("4. List all books")
        print("5. Search for a book")
        print("9. Open Management Menu")
        print("0. Exit")

        choice = input("\nEnter your choice: ")

        if choice == '1':
            check_out_book()
        elif choice == '2':
            check_in_book()
        elif choice == '3':
            list_late_books()
        elif choice == '4':
            list_all_books()
        elif choice == '5':
            search_books()
        elif choice == '9':
            man_menu()
        elif choice == '0':
             print("Exiting program.")
             conn.close()  # Close the database connection before exiting
             sys.exit()  # Terminate the program
        else:
            input("\nInvalid choice, Press Enter to try again.")


if __name__ == "__main__":
    main_menu()

    # Close the database connection when the program ends
    cursor.close()
    conn.close()
