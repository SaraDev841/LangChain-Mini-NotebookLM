from netfree_unstrict_ssl import unstrict_ssl

unstrict_ssl()

from dotenv import load_dotenv

load_dotenv()

from agents import chat


def main() -> None:
	print("simulate chat")
	result = chat.answer("what's your name", "default")
	print(result.text)


if __name__ == "__main__":
	main()
