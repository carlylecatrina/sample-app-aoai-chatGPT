"""Data utilities for index preparation."""
import os
import ast
import markdown
import re
import tiktoken

from tqdm import tqdm
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from dataclasses import dataclass

from typing import List, Dict, Optional, Generator, Tuple
from langchain.text_splitter import MarkdownTextSplitter, RecursiveCharacterTextSplitter, PythonCodeTextSplitter

FILE_FORMAT_DICT = {
        "md": "markdown",
        "txt": "text",
        "html": "html",
        "shtml": "html",
        "htm": "html",
        "py": "python"
    }

SENTENCE_ENDINGS = [".", "!", "?"]
WORDS_BREAKS = list(reversed([",", ";", ":", " ", "(", ")", "[", "]", "{", "}", "\t", "\n"]))

@dataclass
class Document(object):
    """A data class for storing documents

    Attributes:
        content (str): The content of the document.
        id (Optional[str]): The id of the document.
        title (Optional[str]): The title of the document.
        filepath (Optional[str]): The filepath of the document.
        url (Optional[str]): The url of the document.
        metadata (Optional[Dict]): The metadata of the document.    
    """

    content: str
    id: Optional[str] = None
    title: Optional[str] = None
    filepath: Optional[str] = None
    url: Optional[str] = None
    metadata: Optional[Dict] = None

def cleanup_content(content: str) -> str:
    """Cleans up the given content using regexes
    Args:
        content (str): The content to clean up.
    Returns:
        str: The cleaned up content.
    """
    output = re.sub(r"\n{2,}", "\n", content)
    output = re.sub(r"[^\S\n]{2,}", " ", output)
    output = re.sub(r"-{2,}", "--", output)

    return output.strip()

class BaseParser(ABC):
    """A parser parses content to produce a document."""

    @abstractmethod
    def parse(self, content: str, file_name: Optional[str] = None) -> Document:
        """Parses the given content.
        Args:
            content (str): The content to parse.
            file_name (str): The file name associated with the content.
        Returns:
            Document: The parsed document.
        """
        pass

    def parse_file(self, file_path: str) -> Document:
        """Parses the given file.
        Args:
            file_path (str): The file to parse.
        Returns:
            Document: The parsed document.
        """
        with open(file_path, "r") as f:
            return self.parse(f.read(), os.path.basename(file_path))

    def parse_directory(self, directory_path: str) -> List[Document]:
        """Parses the given directory.
        Args:
            directory_path (str): The directory to parse.
        Returns:
            List[Document]: List of parsed documents.
        """
        documents = []
        for file_name in os.listdir(directory_path):
            file_path = os.path.join(directory_path, file_name)
            if os.path.isfile(file_path):
                documents.append(self.parse_file(file_path))
        return documents

class MarkdownParser(BaseParser):
    """Parses Markdown content."""

    def __init__(self) -> None:
        super().__init__()
        self._html_parser = HTMLParser()

    def parse(self, content: str, file_name: Optional[str] = None) -> Document:
        """Parses the given content.
        Args:
            content (str): The content to parse.
            file_name (str): The file name associated with the content.
        Returns:
            Document: The parsed document.
        """
        html_content = markdown.markdown(content)

        return self._html_parser.parse(html_content, file_name)


class HTMLParser(BaseParser):
    """Parses HTML content."""
    TITLE_MAX_TOKENS = 128

    def __init__(self) -> None:
        super().__init__()
        self.token_estimator = TokenEstimator()

    def parse(self, content: str, file_name: Optional[str] = None) -> Document:
        """Parses the given content.
        Args:
            content (str): The content to parse.
            file_name (str): The file name associated with the content.
        Returns:
            Document: The parsed document.
        """
        soup = BeautifulSoup(content, "html.parser")
        try:
            title = next(soup.stripped_strings)
            title = self.token_estimator.construct_tokens_with_size(title, self.TITLE_MAX_TOKENS)

        except StopIteration:
            title = file_name

        text = soup.get_text()

        return Document(content=cleanup_content(text), title=title)


class TextParser(BaseParser):
    """Parses text content."""

    def __init__(self) -> None:
        super().__init__()

    def _get_first_alphanum_line(self, content: str) -> Optional[str]:
        title = None
        for line in content.splitlines():
            if any([c.isalnum() for c in line]):
                title = line.strip()
                break
        return title

    def _get_first_line_with_property(
        self, content: str, property: str = "title: "
    ) -> Optional[str]:
        title = None
        for line in content.splitlines():
            if line.startswith(property):
                title = line[len(property) :].strip()
                break
        return title

    def parse(self, content: str, file_name: Optional[str] = None) -> Document:
        """Parses the given content.
        Args:
            content (str): The content to parse.
            file_name (str): The file name associated with the content.
        Returns:
            Document: The parsed document.
        """
        title = self._get_first_line_with_property(
            content
        ) or self._get_first_alphanum_line(content)

        return Document(content=cleanup_content(content), title=title or file_name)


class PythonParser(BaseParser):
    def _get_topdocstring(self, text):
        tree = ast.parse(text)
        docstring = ast.get_docstring(tree)  # returns top docstring
        return docstring

    def parse(self, content: str, file_name: Optional[str] = None) -> Document:
        """Parses the given content.
        Args:
            content (str): The content to parse.
            file_name (str): The file name associated with the content.
        Returns:
            Document: The parsed document.
        """
        docstring = self._get_topdocstring(content)
        if docstring:
            title = f"{file_name}: {docstring}"
        else:
            title = file_name
        return Document(content=content, title=title)

    def __init__(self) -> None:
        super().__init__()

class ParserFactory:
    def __init__(self):
        self._parsers = {
            "html": HTMLParser(),
            "text": TextParser(),
            "markdown": MarkdownParser(),
            "python": PythonParser()
        }

    @property
    def supported_formats(self) -> List[str]:
        "Returns a list of supported formats"
        return list(self._parsers.keys())

    def __call__(self, file_format: str) -> BaseParser:
        parser = self._parsers.get(file_format, None)
        if parser is None:
            raise UnsupportedFormatError(f"{file_format} is not supported")

        return parser

class TokenEstimator(object):
    GPT2_TOKENIZER = tiktoken.get_encoding("gpt2")

    def estimate_tokens(self, text: str) -> int:
        return len(self.GPT2_TOKENIZER.encode(text))

    def construct_tokens_with_size(self, tokens: str, numofTokens: int) -> str:
        newTokens = self.GPT2_TOKENIZER.decode(
            self.GPT2_TOKENIZER.encode(tokens)[:numofTokens]
        )
        return newTokens

parser_factory = ParserFactory()
TOKEN_ESTIMATOR = TokenEstimator()

class UnsupportedFormatError(Exception):
    """Exception raised when a format is not supported by a parser."""

    pass

@dataclass
class ChunkingResult:
    """Data model for chunking result

    Attributes:
        chunks (List[Document]): List of chunks.
        total_files (int): Total number of files.
        num_unsupported_format_files (int): Number of files with unsupported format.
        num_files_with_errors (int): Number of files with errors.
        skipped_chunks (int): Number of chunks skipped.
    """
    chunks: List[Document]
    total_files: int
    num_unsupported_format_files: int = 0
    num_files_with_errors: int = 0
    # some chunks might be skipped to small number of tokens
    skipped_chunks: int = 0

def get_files_recursively(directory_path: str) -> List[str]:
    """Gets all files in the given directory recursively.
    Args:
        directory_path (str): The directory to get files from.
    Returns:
        List[str]: List of file paths.
    """
    file_paths = []
    for dirpath, _, files in os.walk(directory_path):
        for file_name in files:
            file_path = os.path.join(dirpath, file_name)
            file_paths.append(file_path)
    return file_paths

def convert_escaped_to_posix(escaped_path):
    windows_path = escaped_path.replace("\\\\", "\\")
    posix_path = windows_path.replace("\\", "/")
    return posix_path

def _get_file_format(file_name: str, extensions_to_process: List[str]) -> Optional[str]:
    """Gets the file format from the file name.
    Returns None if the file format is not supported.
    Args:
        file_name (str): The file name.
        extensions_to_process (List[str]): List of extensions to process.
    Returns:
        str: The file format.
    """

    # in case the caller gives us a file path
    file_name = os.path.basename(file_name)
    file_extension = file_name.split(".")[-1]
    if file_extension not in extensions_to_process:
        return None
    return FILE_FORMAT_DICT.get(file_extension, None)

def chunk_content_helper(
        content: str, file_format: str, file_name: Optional[str],
        token_overlap: int,
        num_tokens: int = 256
) -> Generator[Tuple[str, int, Document], None, None]:
    parser = parser_factory(file_format)
    doc = parser.parse(content, file_name=file_name)
    if num_tokens == None:
        num_tokens = 1000000000

    if file_format == "markdown":
        splitter = MarkdownTextSplitter.from_tiktoken_encoder(chunk_size=num_tokens, chunk_overlap=token_overlap)
    elif file_format == "python":
        splitter = PythonCodeTextSplitter.from_tiktoken_encoder(chunk_size=num_tokens, chunk_overlap=token_overlap)
    else:
        splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            separators=SENTENCE_ENDINGS + WORDS_BREAKS,
            chunk_size=num_tokens, chunk_overlap=token_overlap)
    chunked_content_list = splitter.split_text(doc.content)
    for chunked_content in chunked_content_list:
        chunk_size = TOKEN_ESTIMATOR.estimate_tokens(chunked_content)
        yield chunked_content, chunk_size, doc

def chunk_content(
    content: str,
    file_name: Optional[str] = None,
    url: Optional[str] = None,
    ignore_errors: bool = True,
    num_tokens: int = 256,
    min_chunk_size: int = 10,
    token_overlap: int = 0,
    extensions_to_process = FILE_FORMAT_DICT.keys()
) -> ChunkingResult:
    """Chunks the given content. If ignore_errors is true, returns None
        in case of an error
    Args:
        content (str): The content to chunk.
        file_name (str): The file name. used for title, file format detection.
        url (str): The url. used for title.
        ignore_errors (bool): If true, ignores errors and returns None.
        num_tokens (int): The number of tokens in each chunk.
        min_chunk_size (int): The minimum chunk size below which chunks will be filtered.
        token_overlap (int): The number of tokens to overlap between chunks.
    Returns:
        List[Document]: List of chunked documents.
    """

    try:
        if file_name is None:
            file_format = "text"
        else:
            file_format = _get_file_format(file_name, extensions_to_process)
            if file_format is None:
                raise Exception(
                    f"{file_name} is not supported")

        chunked_context = chunk_content_helper(
            content=content,
            file_name=file_name,
            file_format=file_format,
            num_tokens=num_tokens,
            token_overlap=token_overlap
        )
        chunks = []
        skipped_chunks = 0
        for chunk, chunk_size, doc in chunked_context:
            if chunk_size >= min_chunk_size:
                chunks.append(
                    Document(
                        content=chunk,
                        title=doc.title,
                        url=url,
                    )
                )
            else:
                skipped_chunks += 1

    except UnsupportedFormatError as e:
        if ignore_errors:
            return ChunkingResult(
                chunks=[], total_files=1, num_unsupported_format_files=1
            )
        else:
            raise e
    except Exception as e:
        if ignore_errors:
            return ChunkingResult(chunks=[], total_files=1, num_files_with_errors=1)
        else:
            raise e
    return ChunkingResult(
        chunks=chunks,
        total_files=1,
        skipped_chunks=skipped_chunks,
    )

def chunk_file(
    file_path: str,
    ignore_errors: bool = True,
    num_tokens=256,
    min_chunk_size=10,
    url = None,
    token_overlap: int = 0,
    extensions_to_process = FILE_FORMAT_DICT.keys()
) -> ChunkingResult:
    """Chunks the given file.
    Args:
        file_path (str): The file to chunk.
    Returns:
        List[Document]: List of chunked documents.
    """
    file_name = os.path.basename(file_path)
    file_format = _get_file_format(file_name, extensions_to_process)
    if not file_format:
        if ignore_errors:
            return ChunkingResult(
                chunks=[], total_files=1, num_unsupported_format_files=1
            )
        else:
            raise UnsupportedFormatError(f"{file_name} is not supported")

    with open(file_path, "r", encoding="utf8") as f:
        content = f.read()
    return chunk_content(
        content=content,
        file_name=file_name,
        ignore_errors=ignore_errors,
        num_tokens=num_tokens,
        min_chunk_size=min_chunk_size,
        url=url,
        token_overlap=max(0, token_overlap),
        extensions_to_process=extensions_to_process
    )

def chunk_directory(
    directory_path: str,
    ignore_errors: bool = True,
    num_tokens: int = 1024,
    min_chunk_size: int = 10,
    url_prefix = None,
    token_overlap: int = 0,
    extensions_to_process: List[str] = FILE_FORMAT_DICT.keys()
):
    """
    Chunks the given directory recursively
    Args:
        directory_path (str): The directory to chunk.
        ignore_errors (bool): If true, ignores errors and returns None.
        num_tokens (int): The number of tokens to use for chunking.
        min_chunk_size (int): The minimum chunk size.
        url_prefix (str): The url prefix to use for the files. If None, the url will be None. If not None, the url will be url_prefix + relpath. 
                            For example, if the directory path is /home/user/data and the url_prefix is https://example.com/data, 
                            then the url for the file /home/user/data/file1.txt will be https://example.com/data/file1.txt
        token_overlap (int): The number of tokens to overlap between chunks.
    Returns:
        List[Document]: List of chunked documents.
    """
    chunks = []
    total_files = 0
    num_unsupported_format_files = 0
    num_files_with_errors = 0
    skipped_chunks = 0
    for file_path in tqdm(get_files_recursively(directory_path)):
        if os.path.isfile(file_path):
            # get relpath
            url_path = None
            rel_file_path = os.path.relpath(file_path, directory_path)
            if url_prefix:
                url_path = url_prefix + rel_file_path
                url_path = convert_escaped_to_posix(url_path)
            try:
                result = chunk_file(
                    file_path,
                    ignore_errors=ignore_errors,
                    num_tokens=num_tokens,
                    min_chunk_size=min_chunk_size,
                    url=url_path,
                    token_overlap=token_overlap,
                    extensions_to_process=extensions_to_process
                )
                for chunk_doc in result.chunks:
                    chunk_doc.filepath = rel_file_path
                chunks.extend(result.chunks)
                num_unsupported_format_files += result.num_unsupported_format_files
                num_files_with_errors += result.num_files_with_errors
                skipped_chunks += result.skipped_chunks
            except Exception as e:
                if not ignore_errors:
                    raise
                print(f"File ({file_path}) failed with ", e)
                num_files_with_errors += 1
            total_files += 1

    return ChunkingResult(
            chunks=chunks,
            total_files=total_files,
            num_unsupported_format_files=num_unsupported_format_files,
            num_files_with_errors=num_files_with_errors,
            skipped_chunks=skipped_chunks,
        )
