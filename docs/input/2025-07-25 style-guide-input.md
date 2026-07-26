# Style Guide Inputs
Some random points for how I write and organize python code for maintainability. 


- Use descriptive variable, function names that can be understood without adding teh cognitive load of the rest of the file
- Use dependency injection for all external dependencies, either injected in the constructor for a class, or as a function param itself for more one-off functions that don't have an associated class
- Organize most service-level functions into classes, to help conceptually organize them into a single object, and to help with sharing of injected dependencies.
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
