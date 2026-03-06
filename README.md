# Structured-Questionnaire-Answering-Tool

Project Overview

This project is a web application that helps automate the process of answering structured questionnaires using internal company documents. Many companies receive security reviews, vendor assessments, and compliance questionnaires that must be completed using approved documentation.

The goal of this tool is to reduce manual work by using AI to search through reference documents and generate answers for each question. The generated answers include citations from the documents so users can verify where the information came from.

Users can review and edit the answers before exporting the completed questionnaire as a document.

Industry & Fictional Company

Industry: FinTech SaaS

Company: PayFlow AI

PayFlow AI is a fictional fintech SaaS platform that helps businesses monitor digital payments, detect fraudulent transactions, and generate financial insights. The platform integrates with multiple payment gateways and provides secure payment analytics for online businesses.

Features
User Authentication

Users can create an account and log in securely before accessing the system.

Upload Questionnaire

Users can upload a questionnaire file containing multiple questions. The system parses the file and extracts each question automatically.

Upload Reference Documents

Users can upload company documents that act as the source of truth for answering the questionnaire.

AI Answer Generation

The system uses a retrieval-based AI workflow to:

search relevant information from the reference documents

generate answers for each question

attach citations showing which document was used

If the system cannot find supporting information in the documents, it returns:

"Not found in references."

Review and Edit

After answers are generated, users can review and edit the responses before exporting the final document.

Export Completed Questionnaire

The application generates a downloadable document that:

keeps the original questions unchanged

inserts answers below each question

includes citations for each answer

Nice-to-Have Features Implemented
Confidence Score

Each generated answer includes a confidence score based on how closely the retrieved document matches the question.

Evidence Snippets

The system displays a short snippet of the text from the reference document that was used to generate the answer.

Example Workflow

User signs up and logs into the application.

Uploads a questionnaire document.

Uploads company reference documents.

Clicks Generate Answers.

The system retrieves relevant content and generates answers with citations.

User reviews and edits responses if needed.

The final questionnaire is exported as a downloadable document.

Technologies Used

Backend

Python

FastAPI

AI / Retrieval

LangChain

FAISS vector database

Frontend

Streamlit

Database

SQLite

Document Processing

python-docx

pandas

PyPDF

Assumptions

The uploaded reference documents contain accurate and relevant information.

The questionnaire consists of text-based questions.

Each answer must be supported by at least one reference document.

If no relevant information is found, the system should clearly indicate that.

Trade-offs

FAISS was used as a lightweight vector database instead of a production-scale solution.

The user interface was kept simple to focus more on functionality and AI workflow.

Authentication is basic and suitable for demonstration purposes.

Future Improvements

If more time were available, the following improvements could be added:

Support for larger document collections

Better answer ranking and citation accuracy

Multi-user collaboration

Document version tracking

Improved UI and dashboard analytics

Support for additional file formats

How to Run the Project

Clone the repository:

git clone - https://github.com/dharmesh1510/Structured-Questionnaire-Answering-Tool.git

Install dependencies:

pip install -r requirements.txt

Run the application:

streamlit run app.py

