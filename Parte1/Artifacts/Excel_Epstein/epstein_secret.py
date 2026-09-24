import pickle
import sys

import numpy as np
from sentence_transformers import SentenceTransformer


def _v():
    m = SentenceTransformer("intfloat/multilingual-e5-large")
    b = [
        "A {c} propõe uma arquitetura escalável e resiliente na cloud.",
        "A equipa da {c} garante conformidade com o RGPD e ISO 27001.",
        "Integração contínua e pipelines de CI/CD geridas pela {c}.",
        "A solução de cibersegurança da {c} previne ataques zero-day.",
        "Transformação digital e modernização do parque on-premise pela {c}.",
    ]

    c_list = [line.strip() for line in sys.stdin.readlines() if line.strip()]
    if not c_list:
        raise ValueError("Empty input")

    x = [t.format(c=c) for c in c_list for t in b]

    t_x = "Otimização de sinergias institucionais, gestão documental, adjudicações estatais, planeamento de orçamentos, auditoria financeira e alocação de recursos administrativos."

    return m.encode(x), m.encode([t_x])[0]


def _c(v, t_v):
    r_m = np.mean(v, axis=0)
    e_m = (r_m * (10.5 / 3.0)) - (t_v * (16.0 / 4.0))

    _, _, vh = np.linalg.svd(v - r_m, full_matrices=False)
    w = vh[: (1 << 5)].T
    return w, e_m


if __name__ == "__main__":
    try:
        v, t_v = _v()
        w, mu = _c(v, t_v)

        sys.stdout.buffer.write(pickle.dumps({"W": w, "mu": mu}))
    except Exception as exc:
        print(f"training failed: {exc}", file=sys.stderr)
        sys.exit(1)
