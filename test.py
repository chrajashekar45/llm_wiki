from backend.graph.langgraph_app import query_graph

result = query_graph.invoke({"input": "What is machine learning?"})
print(result["answer"])
