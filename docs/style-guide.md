# Style Guide
Rules for how to organize code in this project, and on how differnet components should be implemented

## Folder Structure
- Project folder structure uses 1 folder for each type of component:
    ```
    src/forte/
        main.py         # Composition root
        controller/     # Implement user interfaces, triggers
        service/        # Implement core business logic, and abstract entities
        interface/      # Definitions of interfaces needed by the service layer
        client/         # Concrete implementations of interface/ abstractions
        model/          # Core data types used by all other folders
    ```
- This folder structure is heavily inspired by more object-oriented languauges like C#, Go, and Java, but lends itself well to building more complicated applications. We recognize this is not 'pythonic'

## 3 Layer Architecture
- Break each feature into 3 layers:
  - service: the abstract function being implemented (e.g. "ingest_doc()"), with all core business logic on abstract entities
  - client: the concrete implementations of abstract dependencies defined in the service layer (e.g. "class FSDocStore")
  - controller: the interfaces exposed to the user for triggering service functions (e.g. Click CLI wrappers).
- Example, a Configuration feature (in pseudocode):
  - service: 
    ```
    ConfigService:
        - init_from_provider(IConfigProvider)
        - get(key) 
    
    IConfigProvider:
        get_configs(): map[string]string
    ```
  - client:
    ```
    DotEnvConfigProvider:
        get_config() # Reads configs from .env files in the current root
    ```
  - controller:
    ```
    CliController:
        init(ConfigService) # called on app start, with proper config service
    ```
- Controllers call services, which call clients. Clients should never call service functions, and services should never call controller functions. 
- Clients should implement low-level operations against external dependencies with very little business logic applied - except in translating abstract objects into objects understood by the external integration. 
- Use classes to encapsulate most features, because using classes helps with instantiation and wiring, and also testability. You can do DI with functions definitely, but classes have a cleaner separation between "this is a dependency" (passed in the constructor) and "this is an function parameter" (passed in the function call)
- All service functions should be unit tested using mock implementations of clients, with the test suite directly calling functions as if it were the controller. 
- Clients should be unit tested as much as is reasonable, but full testing of external dependencies should be done in e2e tests. 
- Controllers should also be unit tested as much as is reasonable, if possible using a real user-interface but a mock service. 


## Writing Controllers
- Controllers implement the user-interface / trigger-point of a feature, but should ONLY implement that. They should take in services as dependencies, and pass on actual business logic to the service via function call.
- Put all controllers in the `controller` directory
- Name each controller `<interface><service>Controller`. For example `CliDocController`, meaning this controller implements the CLI interface for the DocService.
- Define controllers as classes, with necessary services injected in teh constructor (top-level wiring happens in a main.py)
- For CLI controllers, build the `click.Group` in a `group()` method with nested command functions that just unpack CLI args and delegate to a private method of the same name on the controller (e.g. `schema.command("add")` calls `controller._add(...)`). Keep all real logic, error handling, and echoing in the private method, not the nested Click callback.
- Wrap every service call in a `try/except`, catching the feature's base error class (e.g. `SchemaError`) together with `VaultNotFoundError`, and re-raise as `click.ClickException(str(e))`. Don't catch specific subclasses individually.

## Writing Services
- Services implement the core functions exposed by the application, and operate solely on abstract data models, and injected interfaces for dependencies. 
- Put all services in the `service` directory
- Services will need external integrations with clients, these should be injected as implementations of interfaces. Define the interfaces in the `interface` directory
- Name each service based on a grouping of features / functionality. e.g. "DocService" for all operations related to document management. 
- Define services as classes, with necessary interfaces injected in the constructor (top-level wiring happens in a main.py)
- Validate all inputs fully before making any write calls to a client. If validation fails partway through, no client method should have been called yet (e.g. `SchemaService.create_schema` runs every check on `name` and `field_names` before ever touching `schema_db`). This avoids partial writes that would need cleanup.
- Every method that can raise must document exactly which exception types it raises, and under what condition, in its docstring's `Raises:` section — not just "raises on invalid input".

## Writing Interfaces
- Name each interface `I<Noun>`, e.g. `ISchemaDb`. Its methods describe storage/IO operations only — no business logic or validation.
- Interface methods don't raise feature errors themselves (no `Raises:` in their docstrings); validation and error-raising happens in the service that calls them.
- Order interface (and client) methods consistently: an existence check first (e.g. `check_exists`), then CRUD in create/read/list/delete order, then any extra query methods (e.g. `count_entities`) last.

## Writing Clients
- Clients give concrete implementations of the abstract interfaces defined in the `interface` directory, used by services.
- Each client should focus on 1 external dependency to implement the interface. If multiple are needed, likely the interface is too high-level or too broad. 
- Name clients `<technology/dependency><Interface>` e.g. `IConfigProvider` -> `DotenvConfigProvider`


## Python style conventions
- Each function should start with a google-style doc-string:
    ```
    def my_function(a, b):
        """
        Multiplies a and b together

        Args:
            a (int): A number
            b (int): A number
        
        Returns:
            (int) The product of a and b
        
        Raises:
            InputError: if either a or b is not a number
        """
    ```
- NOTE: class __init__ functions don't need docstrings. It's obvious what they do
- Each class should also start with a multiline doc string describing what is contained in that class, and what it does.
- Private module-level constants (e.g. regexes, reserved-value sets) get a `_leading_underscore`, `UPPER_SNAKE_CASE` name and a one-line comment above explaining what they're for.

## Exceptions
- Each feature defines its exceptions in its `model/` file (not in `service/`), as one base error class per feature plus specific subclasses. E.g. `model/schema.py` defines `SchemaError` and subclasses `InvalidSchemaError`, `SchemaExistsError`, `SchemaNotFoundError`, `SchemaInUseError`.
- The base class's docstring is just `"""Base class for <feature> errors."""`; each subclass's docstring states the one condition that raises it.
- Only services raise these exceptions; clients and interfaces don't.