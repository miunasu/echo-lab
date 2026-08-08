        """Command-line entry for demo_json_pkg."""

        from __future__ import annotations


        def main() -> None:
            from demo_json_pkg.core import hello
print(hello())


        if __name__ == "__main__":
            main()
