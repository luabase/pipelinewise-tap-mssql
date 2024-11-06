import backoff
import pymssql
import pyodbc
import singer

LOGGER = singer.get_logger()

@backoff.on_exception(backoff.expo, (pymssql.Error, pyodbc.Error), max_tries=5, factor=2)
def connect_with_backoff(connection):
    warnings = []
    with connection.cursor():
        if warnings:
            LOGGER.info(
                (
                    "Encountered non-fatal errors when configuring session that could "
                    "impact performance:"
                )
            )
        for w in warnings:
            LOGGER.warning(w)

    return connection

class MSSQLConnection:
    def __init__(self, config):
        self.driver = config.get("driver", "pymssql")
        self.connection = self._create_connection(config)

    def _create_connection(self, config):
        if self.driver == "pymssql":
            return pymssql.connect(**self._pymssql_args(config))
        elif self.driver == "pyodbc":
            return pyodbc.connect(self._pyodbc_conn_str(config))
        else:
            raise ValueError(f"Unsupported driver: {self.driver}")

    def _pymssql_args(self, config):
        return {
            "user": config.get("user"),
            "password": config.get("password"),
            "server": config["host"],
            "database": config["database"],
            "charset": config.get("characterset", "utf8"),
            "port": config.get("port", "1433"),
            "tds_version": config.get("tds_version", "7.3"),
        }

    def _pyodbc_conn_str(self, config):
        return (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={config['host']},{config.get('port', '1433')};"
            f"DATABASE={config['database']};"
            f"UID={config.get('user')};"
            f"PWD={config.get('password')};"
            f"MultiSubnetFailover={config.get('multi_subnet_failover', 'Yes')};"
        )

    def __enter__(self):
        return self.connection.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        return self.connection.__exit__(exc_type, exc_value, traceback)

    def cursor(self):
        return self.connection.cursor()

    def close(self):
        return self.connection.close()

def make_connection_wrapper(config):
    class ConnectionWrapper(MSSQLConnection):
        def __init__(self, *args, **kwargs):
            super().__init__(config)
            connect_with_backoff(self.connection)

    return ConnectionWrapper

def ResultIterator(cursor, arraysize=1):
    while True:
        results = cursor.fetchmany(arraysize)
        if not results:
            break
        for result in results:
            yield result
