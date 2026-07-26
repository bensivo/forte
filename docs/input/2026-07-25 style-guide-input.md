# Style Guide Inputs
Some random points for how I write and organize python code for maintainability. My 'python' code is admittedly not very 'pythonic', but I'm okay with that. I borrow lots of organizational ideas from more staticly-typed, object-oriented programming languages that just make sense to me, and I've found help me to orgniaze any codebase at scale, and keep changes from sprawling. It's not idiomatic, it's not pythonic, but it works better for me. 

- Use descriptive variable, function names that can be understood without adding the cognitive load of the rest of the file
- Use dependency injection for all external dependencies, either injected in the constructor for a class, or as a function param itself for more one-off functions that don't have an associated class
- Organize most functions into classes, to help conceptually organize them into a single object, and to help with sharing of injected dependencies.
- Stateless, one-off functiosn can be defined top-level without a class, if it makes sense. That being said, a Utils class with static functions works just as well and still helps with code organization
- Organize your codebase into 3 layers:
  - controller: the 'driver' layer of the app, where user interfaces are implemented, like REST controllers, CLI parsing, etc.. Handles receiving requests from the user, parsing the request from whatever format it came in, calling a service function, and then returning the response to the user. 
  - service: the core business logic of your application, exposes core application functions, but operates using purely abstract interfaces for external dependencies
  - adapter: implementations of the dependency interfaces defined in teh service layer. For example, 'service' might define a 'IUsersRepository'

  - Example:
    - HttpUsersController - defines the GET /users endpoint, parses HTTP requests, and calls UsersService.getAll()
        - usersService: IUsersService
    - IUsersService - defines the getAll() function. Exists mostly so that controllers can be tested in isolation, but also for seamless version upgrades (you can put version numbers on interfaces, e.g. 'IUsersServiceV1')
    - UsersService - implements the getAll() function, and uses injected adapters to implement it, adding any business logic on top of returned results
        - usersDb: IUsersDb
    - IUsersDb - defines the abstract functions that any usersDb needs to implement
    - SqliteUsersDb - implements the IUsersDb interface using a sqlite database

    - Application - The orchestration layer that instantiates everything in the right order, and runs the app
        - httpUsersController
        - usersService
        - sqliteUsersDb

    - For small apps, you can just have 3 folders: `controller, service, adapter`, but for larger apps, you might break down code by domain modules, and have separate controllers, services, and adapters implemented per module. 

- All classes should have a docstring describing what the class does / contains in this app

- All functions should have a docstring using the google format:
  ```
  def multiply(a, b):
  """
  This is an example of Google style.

  Args:
      param1: This is the first param.
      param2: This is a second param.

  Returns:
      This is a description of what is returned.

  Raises:
      KeyError: Raises an exception.
  """
  ```
    - The 'Raises' part is optional, only if it explicitly raises somthing

- Define classes in their own file, with the filename matching the class name. 

- Name interfaces starting with an I, e.g. 'IUsersService', and impelment them using typing Protocols