from flask import Flask, render_template, jsonify, request,session, redirect,url_for
from flask import flash
from flask_sqlalchemy import SQLAlchemy
import bcrypt
import markdown2
from functools import wraps
from src.helper import text_split, load_pdf_file, download_hugging_face_embeddings
from langchain_pinecone import PineconeVectorStore
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import OpenAI
from dotenv import load_dotenv
from src.prompt import *
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = 'This_is_a_assignment_project'

# Rate Limiter
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# Rate Limit Key Func (Per-Session or IP Fallback)
def get_user_identifier():
    return session.get('email') or get_remote_address()

limiter = Limiter(
    app=app,
    key_func=get_user_identifier,
    default_limits=[]
)

@app.errorhandler(429)
def ratelimit_exceeded(e):
    return jsonify({"error": "Rate limit exceeded. Please wait before trying again."}), 429


# Autherization Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            flash("You need to login first.")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function



#Sqlite Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key= True)
    name = db.Column(db.String(100), nullable = False)
    email = db.Column(db.String(100), unique = True)
    password = db.Column(db.String(100))

    def __init__(self,email,password,name):
        self.name = name
        self.email = email
        self.password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self,password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password.encode('utf-8'))

with app.app_context():
    db.create_all()        

# api keys
PINECONE_API_KEY = os.environ.get('PINECONE_API_KEY')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')


os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY
os.environ["DEEPSEEK_API_KEY"] = DEEPSEEK_API_KEY


# Ai and data retrieval
embeddings = download_hugging_face_embeddings()
index_name = "aimedication"

#Embed each chunk and upsert the embeddings into your Pinecone index.
docsearch = PineconeVectorStore.from_existing_index(
    index_name=index_name,
    embedding=embeddings,
)


retriver = docsearch.as_retriever(search_type="similarity", search_kwargs={"k":3})


from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    api_key= DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
    model="deepseek-chat",
    temperature=0.4,
    max_tokens=500
)



prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("human", "{input}"),
    ]
)

question_answer_chain = create_stuff_documents_chain(llm, prompt)
rag_chain = create_retrieval_chain(retriver, question_answer_chain)



#Routes

@app.route('/')
def index():
    if 'email' in session:
        return redirect(url_for('medication'))
    return render_template('register.html')



# Route for user to register
@app.route('/register', methods = ["GET", "POST"])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        new_user = User(name = name, email = email, password = password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registered successfully! Please login.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')




# Route for user to login
@app.route('/login', methods = ["GET", "POST"])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email = email).first()

        if user and user.check_password(password):
            session['name'] = user.name
            session['email'] = user.email
            # session['password'] = user.password

            return redirect('/medication')
        else:
            flash("Invalid email or password", "danger")
            return render_template('login.html', error='Invalid user')

    return render_template('login.html')


# Route for user to access the application
@app.route("/medication", methods = ["GET", "POST"])
@limiter.limit("5 per 10 minutes")
@login_required
def medication():
    if request.method == "POST":
        msg = request.form.get("msg")
        if not msg:
            return "No message received", 400
    
        print("Received message:", msg)

        #AI = response
        response = rag_chain.invoke({"input": msg})
        raw_answer = response["answer"]
    
        # Convert Markdown to clean HTML
        html_answer = markdown2.markdown(
            raw_answer,
            extras=["fenced-code-blocks", "tables", "break-on-newline"]
        )

        return html_answer
        
    
    # Get user info from session
    name = session.get("name")
    email = session.get("email")
    return render_template("medication.html", name = name , email = email)



# Route for user to logout
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('login'))

    




if __name__ == '__main__':
    app.run(host="0.0.0.0", port= 8000, debug=True)






