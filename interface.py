from datetime import datetime, timedelta 
import gradio as gr
import openai
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, load_index_from_storage
from llama_index.core.llms import ChatMessage, MessageRole
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os
import logging
import sys
import io
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"), server_api=ServerApi('1'))
db = client[os.getenv("DB_NAME")]
collection = db[os.getenv("COLLECTION_NAME_A")]

task = "The function 'time_to_seconds', which should take a string time as an input parameter. The string specifies a participant's finishing time in an event (e.g., holding their breath for as long as possible) and will have the following format: min:sec.hundredths. The function should convert this string into a floating-point number in the format seconds.hundredths and return this floating-point number."

def store_submission(user_id, code_input, code_help, submit_type):
    if not hasattr(store_submission, "input_number"):
        store_submission.input_number = 0
    store_submission.input_number += 1

    document = {
        "user_id": user_id,
        "input_number": store_submission.input_number,
        "submit_type": submit_type,
        "time": datetime.utcnow() + timedelta(hours=1),
        "code_input": code_input,
        "code_help": code_help,
    }
    collection.insert_one(document)
    print(f"Stored {submit_type} submission for user {user_id} with input number {store_submission.input_number}")


def chat_pdf(message, history=None):
    if history is None:
        history = []
    def message_generator():
        messages = []
        for message_pair in history:
            if message_pair[0] is not None:
                messages.append(ChatMessage(role=MessageRole.USER, content=message_pair[0]))
            if message_pair[1] is not None:
                messages.append(ChatMessage(role=MessageRole.ASSISTANT, content=message_pair[1]))
        print(messages)
        return messages

    if not os.path.exists('./storage'):
        documents = SimpleDirectoryReader('./data').load_data()
        index = VectorStoreIndex.from_documents(documents)
        index.storage_context.persist()
    else:
        storage_context = StorageContext.from_defaults(persist_dir="./storage")
        index = load_index_from_storage(storage_context)

    query_engine = index.as_chat_engine(chat_mode='best', verbose=True)
    response = query_engine.stream_chat(message, message_generator())

    response_text = []
    for text in response.response_gen:
        response_text.append(text)
        print(response_text)
    return ''.join(response_text)

def execute_code(code, user_id):
    output_io = io.StringIO()
    try:
        sys.stdout = output_io
        exec(code, {})
    except Exception as e:
        return f"Error: {e}"
    finally:
        sys.stdout = sys.__stdout__ 

    store_submission(user_id, code, None, "execute")
    return output_io.getvalue()

def submit_code(code, user_id):
    store_submission(user_id, code, None, "submit")
    
with gr.Blocks() as demo:
    code_input_var = gr.State()
    chat_output_var = gr.State()
    gr.Label(task)
    user_id_input = gr.Textbox(label="User ID", placeholder="Enter your user ID")
    with gr.Row():
        code_field1 = gr.Code(language="python")
        code_output_area = gr.TextArea(label="Code Output")
    chat_output_area = gr.TextArea(label="Task assistance")
    assistance_button = gr.Button(value="Get help")
    execute_button = gr.Button("Execute Code")
    submit_button = gr.Button("Submit Code")
    

    execute_button.click(
        execute_code,
        inputs=[code_field1, user_id_input],
        outputs=code_output_area
    )

    submit_button.click(
    submit_code,
    inputs=[code_field1, user_id_input],
    outputs=code_output_area
    )
    
    def code_input_function(code_input, code_input_state, user_id):
        message = f"""I'm tackling a programming challenge and require targeted assistance within this restricted setting, akin to an exam scenario. The task at hand is: {task}. As an example, it could involve basic arithmetic operations in Python, such as adding two numbers.
            My current attempt looks like this: {code_input}, and is the only code you should consider for your answer. Any other code than {code_input} should not be used for your response. Please write down the code you are evaluating at the start of your answer for me, so that I can see which code you have access to. I'm not seeking a direct solution but rather:
            1) Detailed Analysis: Could you examine my code and pinpoint exactly where and why it might not be effectively addressing the task? Highlight specific lines or logic that could be improved, focusing on adherence to Python's best practices and the task's specific requirements. Do not provide any code, just text explanations.
            2) Conceptual Guidance: What key Python concepts, functions, or operators should I focus on to better align with the task? If the task involves arithmetic operations, for instance, an exploration of how Python manages these operations, including operator precedence and the handling of different data types, would be crucial. Do not provide any code, just text explanations.
            3) Actionable Suggestions: Given my current implementation, what concrete steps can I take to refine my logic or code structure? Suggestions should help me rethink my approach or better utilize Python's capabilities to meet the task's goals more effectively. Do not provide any code, just text explanations. If the provided code already solves the given task in any way, do not give any action suggestions.
            I aim to enhance my coding skills and grasp the underlying programming principles through this challenge. Your advice on approaching this problem thoughtfully and efficiently, using only the information and tools at our immediate disposal, would be greatly appreciated. Remember to not give me any code as a part of your answer.
            If the provided answer from the user solves the given task (no matter the quality of the solution), this should be told to the user and they should not receive any feedback."""
        response = (chat_pdf(message, []))
        store_submission(user_id, code_input, response, "get_assistance")
        return code_input, response
    
    assistance_button.click(
        code_input_function, 
        inputs=[code_field1, code_input_var, user_id_input],
        outputs=[code_field1, chat_output_area]
    )

if __name__ == "__main__":
    openai.api_key = os.getenv("OPENAI_API_KEY")
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    demo.queue().launch()
