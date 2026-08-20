from backend.retrieval.search import _branch_vector
try:
    res = _branch_vector("the red house", 5)
    print("Results:", len(res))
    for r in res:
        print(r)
except Exception as e:
    print("Error:", e)
