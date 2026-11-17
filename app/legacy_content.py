COURSES = {
    "ml_overfitting": {
        "title": "Machine Learning: Overfitting",
        "course": "Machine Learning",
        "question": "A model gets 98% training accuracy but only 65% validation accuracy. What is happening, and what could improve generalization?",
        "reference": "A large training-validation performance gap suggests overfitting: the model has learned training-specific patterns that do not transfer to unseen data. Potential mitigations include simpler models, regularization, more representative training data, early stopping and careful validation. These results alone cannot identify the unique cause.",
        "concepts": ["overfitting", "generalization", "validation", "regularization"],
        "solution_markers": ["overfitting", "regularization", "early stopping", "simpler model"],
        "steps": [
            "What do the training and validation scores tell you about how the model behaves on unseen examples?",
            "How might fitting the training examples very closely affect performance on new data?",
            "Which approach could help limit the model's complexity, and why might that help?"
        ],
        "hint": "Compare how the model behaves on the data it saw during training with data it did not see.",
        "quiz": "A classifier has 96% training accuracy and 61% test accuracy. What generalization problem is suggested? Give one plausible way to reduce it.",
        "quiz_terms": [["overfit", "memor"], ["regulariz", "early stop", "simpl", "more data", "augment"]]
    },
    "cn_gateway": {
        "title": "Computer Networks: Default Gateway",
        "course": "Computer Networks",
        "question": "A PC can ping devices in its own subnet, but cannot reach a server on another subnet. Which configuration should you investigate first, and why?",
        "reference": "If local subnet communication succeeds but off-subnet communication fails, check the host's default gateway and routing, as well as subnet mask and external reachability. The default gateway routes traffic destined outside the host's local network.",
        "concepts": ["subnet", "default gateway", "routing", "local network"],
        "solution_markers": ["default gateway", "gateway address", "routing table"],
        "steps": [
            "What is different about sending a packet to a device in the same subnet versus another subnet?",
            "Which network component handles traffic whose destination is outside the local network?",
            "What address or routing configuration would the host need to reach that component?"
        ],
        "hint": "Consider how a host decides where to send packets that cannot be delivered on its local subnet.",
        "quiz": "A laptop reaches its local printer but cannot access a host on a different IP network. What configuration could explain this, and what does it do?",
        "quiz_terms": [["gateway", "route"], ["other network", "another network", "outside", "different subnet", "forward", "router"]]
    }
}
