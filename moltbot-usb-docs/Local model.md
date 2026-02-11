I want to create my own optimized digital helper; You can review the directory we're in to get an idea of the project right now; The next thing I want to do is use a linux server that will primarily be interacted with over messages via Signal (already set up). Lets ignore the openclaw idea for now and try to build something from scratch using the oLlama model we have. 

The main things I want to figure out is how to implement persistance; I want this ust to boot into an interactable bot immediately that remembers when it was last operating (even if that's a different machine) 

Running constantly is a cli that is reporting updates on what the machine is currently doing; a text reciever is monitoring signal for incomming messages; messages are turned into tasks and added into some master queue of tasks (based on priority). Tasks are further broken down into indicidual skills, which are chaied together to complete a task. 

Skills I imagine are highly specific scripts that will have to communicate their outputs with the model that is "running" the task. 

There are a few basic ones I want right now:
- Optimizeation skill -> optimizes the system for the hardware it's on
- current task report skill -> generates a short report about what is currently being done
-  signal message skill -> may be used to send regular updates in future, I want it to chain well after the current task report is generated
  
  I should be able to chat via signal to the system constantly, while complex tasks run in the background
  
  do you have any suggestions for a system that could do this? 
  
  I kind of want it to be able to copy the basic functionality of warp & openclaw directly from the cli or signal chat. The focus must be on optimizing for low spec hardware
  
  do you have any clarifying questions?
  
  How should we proccede?
  
  
  