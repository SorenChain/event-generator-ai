# pip install langchain-perplexity
from langchain_perplexity import ChatPerplexity
from langchain_core.prompts import ChatPromptTemplate

# Optionally, set your API key directly
chat = ChatPerplexity(
    temperature=0.2,
    pplx_api_key="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",  # Or omit if set as env variable
    model="sonar-pro"  # Use a valid model name
)

system = "You are a helpful assistant."
human = "{input}"

prompt = ChatPromptTemplate.from_messages([
    ("system", system),
    ("human", human)
])

chain = prompt | chat

response = chain.invoke({"input": "Who will win The Open in 2025, give me the probability as well with percentage which totalling 100%?"})

print(response.content)
