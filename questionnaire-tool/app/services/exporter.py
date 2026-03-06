import csv
import io
from typing import List

from openpyxl import Workbook

from .. import models


def citation_text(citations: List[str]) -> str:
    return "; ".join(citations)


def answer_for_export(answer: models.Answer) -> str:
    return (answer.edited_answer or answer.generated_answer).strip()


def to_csv_rows(questions: List[models.Question]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Question", "Answer", "Citations", "Confidence"])
    for question in questions:
        answer = question.answer
        if not answer:
            writer.writerow([question.text, "", "", ""])
            continue
        writer.writerow(
            [
                question.text,
                answer_for_export(answer),
                citation_text(answer.citations or []),
                f"{answer.confidence:.2f}",
            ]
        )
    return output.getvalue()


def to_xlsx_bytes(questions: List[models.Question]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Questionnaire Output"
    ws.append(["Question", "Answer", "Citations", "Confidence"])
    for question in questions:
        answer = question.answer
        if not answer:
            ws.append([question.text, "", "", ""])
            continue
        ws.append(
            [
                question.text,
                answer_for_export(answer),
                citation_text(answer.citations or []),
                round(answer.confidence, 2),
            ]
        )
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()
