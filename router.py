from fastcoref import FCoref

model = FCoref(device="cpu")

texts = [
    """I'm working on a robot.
It's for avalanche rescue.
We're using a helical drive."""
]

pred = model.predict(texts=texts)

print(pred[0].get_clusters())