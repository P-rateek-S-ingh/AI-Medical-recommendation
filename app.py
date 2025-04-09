from flask import Flask, render_template, jsonify, request,session, redirect
from flask_sqlalchemy import SQLAlchemy
import bcrypt
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




from functools import wraps
from flask import redirect, url_for, session, flash

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            flash("You need to login first.")
            return redirect('login')
        return f(*args, **kwargs)
    return decorated_function




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


PINECONE_API_KEY = os.environ.get('PINECONE_API_KEY')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')


os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY
os.environ["DEEPSEEK_API_KEY"] = DEEPSEEK_API_KEY

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


@app.route('/')
def index():
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
        return redirect(' login')

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
            return render_template('login.html', error='Invalid user')

    return render_template('login.html')


# Route for user to access the application
@app.route("/medication", methods = ["GET", "POST"])
@login_required
def medication():
    if request.method == "POST":
        msg = request.form.get("msg")
        if not msg:
            return "No message received", 400
        print("Received message:", msg)
        response = rag_chain.invoke({"input": msg})
        return str(response["answer"])
    
    return render_template("medication.html")

# Route for user to logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

    




if __name__ == '__main__':
    app.run(host="0.0.0.0", port= 8000, debug=True)






