import os
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, DocumentAnalysisFeature, ContentFormat

# 環境変数を取得する
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
AZURE_DOCUMENT_INTELLIGENCE_KEY = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")
AZURE_DOCUMENT_INTELLIGENCE_MODEL = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_MODEL", "prebuilt-layout")
AZURE_DOCUMENT_INTELLIGENCE_LOCALE = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_LOCALE", "ja-JP")

# Azure Document Intelligence クライアントを初期化する
doci_client = DocumentIntelligenceClient(
    endpoint=AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT,
    credential=AzureKeyCredential(AZURE_DOCUMENT_INTELLIGENCE_KEY),
)


def get_ocr_file(storage_url: str) -> dict:
    """
    Document Intelligence でOCRを実行する

    Args:
        storage_url (str): ストレージのURL

    Returns:
        dict: OCR結果
    """

    poller = doci_client.begin_analyze_document(
        AZURE_DOCUMENT_INTELLIGENCE_MODEL,
        analyze_request=AnalyzeDocumentRequest(url_source=storage_url),
        locale=AZURE_DOCUMENT_INTELLIGENCE_LOCALE,
    )
    ocr_result = poller.result().as_dict()
    return ocr_result


def parse_ocr_result(ocr_result: dict, remove_selection_mark: bool = True) -> str:
    """
    Document Intelligence で処理した結果をHTMLに変換する

    Args:
        ocr_result (dict): Document Intelligence で処理した結果
        remove_selection_mark (bool): セレクションマークを削除するかどうか

    Returns:
        str: HTML形式のコンテンツ
    """

    # Paragraph を削除する ID 一覧を初期化する
    skip_paragraph_ids = []

    # 各テーブルを挿入する位置(ParagraphのID)を特定する
    # また先頭以外の Paragraph 情報は削除するため、そのIDを記録する
    table_paragraph_ids_map = {}
    for table in ocr_result["tables"]:
        elements = sum([t["elements"] for t in table["cells"] if "elements" in t], [])
        element_ids = [int(e.replace("/paragraphs/", "")) for e in elements]
        element_ids = list(set(element_ids))
        element_ids.sort()
        if len(element_ids) == 0:
            continue
        table_paragraph_ids_map[element_ids[0]] = table
        skip_paragraph_ids.extend(element_ids[1:])

    # 各 Paragraph を処理する
    contents = []
    for i, p in enumerate(ocr_result["paragraphs"]):

        # 図形といったスキップ良い段落の場合は処理しない
        if i in skip_paragraph_ids:
            continue

        # テーブルの場合の処理
        if i in table_paragraph_ids_map:
            table = table_paragraph_ids_map[i]
            content = __convert_table_to_html(table)
        # テーブルまたは画像以外の場合の処理
        else:
            role = p["role"] if "role" in p else ""

            # ヘッダー/フッター/ページ番号の場合はスキップする
            if role in ["footnote", "pageHeader", "pageFooter", "pageNumber"]:
                continue

            # タイトルと見出しをHTML変換する
            content = p["content"]
            if role == "title":
                content = f"<h1>{content}</h1>"
            elif role == "sectionHeading":
                content = f"<h2>{content}</h2>"

        # 指定があればセレクションマークは含めない
        if remove_selection_mark:
            content = content.replace(":unselected:", "").replace(":selected:", "")

        # コンテンツとして格納する
        contents.append(content)

    # 出力するコンテンツを返す
    content = "\n".join(contents)
    return content


def __convert_table_to_html(table: dict) -> str:
    """
    Document Intelligence で取得したテーブル情報をHTMLに変換する

    Args:
        table (dict): Document Intelligence で取得したテーブル情報

    Returns:
        str: HTML形式のテーブル情報
    """

    cells = table["cells"]
    cell_count = 0
    brank_cell_count = 0
    html = "<table>"
    for row_index in range(0, table["rowCount"]):
        # 各行ごとにセルを処理する
        html += "<tr>"
        row_cells = [cell for cell in cells if cell["rowIndex"] == row_index]
        for row_cell in row_cells:
            cell_content = row_cell["content"]
            # cell_content = cell_content.replace("\n", "") # テーブル内の改行を削除する

            # セルの種類によってタグを変える
            tag = "th" if "kind" in row_cell and row_cell["kind"] == "columnHeader" else "td"

            # セルの結合数によってcolspanを設定する
            column_span = f' colspan="{row_cell["columnSpan"]}"' if "columnSpan" in row_cell else ""

            # セルの結合数によってrowspanを設定する
            row_span = f' rowspan="{row_cell["rowSpan"]}"' if "rowSpan" in row_cell else ""

            # セルのHTMLを追記する
            html += f"<{tag}{column_span}{row_span}>{cell_content}</{tag}>"

            # セル数と空白セル数をカウントする
            cell_count += 1
            if len(cell_content) == 0:
                brank_cell_count += 1

        html += "</tr>"
    html += "</table>"

    # 埋め込まれている画面を無理やりテーブルとして抽出している場合、
    # HTMLテーブルとして成立していないことがあるため、出力しないようにする
    brank_rate = brank_cell_count / cell_count
    if brank_rate > 0.5:
        return ""

    return html
