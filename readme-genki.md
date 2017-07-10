https://quantiacs.com/Blog/Intro-to-Algorithmic-Trading-with-Heikin-Ashi.aspx

NumericRef (Reserved Word)
 Disclaimer 
Reserved word used to define the data type of an input to a function that expects a number passed by reference.
InputName(NumericRef); 
Remarks
A function Input is declared as a NumericRef when it is passing in a numeric variable by reference.  Any changes to the value within the function will be reflected in the referenced value declared in the calling code.
Examples
Input: PassedValues(NumericRef); 
indicates that a numeric value is being passed into the function by reference through the Input PassedValues.

========================================================================

Return (Reserved Word)
 Disclaimer 
The reserved word Return terminates execution of the method in which it appears and returns control to the method caller. It can also return the value of the optional expression. If the method is of the type void, the return statement can be omitted.
If the return statement is inside a try block, the finally block, if one exists, will be executed before control returns to the calling method.
Syntax
Method Double GetRange
return High-Low;
end;
Remarks
If the method return type is not void, then the method can return the value using the return keyword.  The returned value needs to match the return type specified when declaring the method.  
If the return type is void, a return statement with no value is still useful to stop the execution of the method. Without the return keyword, a method will stop executing when it reaches the end of the code block. Methods with a non-void return type are required to use the return keyword to return a value.
