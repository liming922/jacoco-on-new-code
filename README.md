# jacoco-on-new-code


Jacoco is a great tool,  it would tell you which lines code have not been covered by unit testing.

However, when there is a huge project,  thousands lines of code.   And in my pull request,  I only touch 2 or 3 files. 
In this case, I just want to know if my new code have good coverage or not.

I hope a tool can tell me the code coverage about my new code, then I have to search whole jacoco code coverage report to find my answer, because jacoco can only generate report for whole project,  it can not for my 2 files only.

This scrpit solves my issue,  it can extract the new code coverage only. 
It need 2 inputs: 
1.  the whole jacoco report
2.  the git diff files,   it can be got by 'git diff'

then it would generate a super small report for your code only,   if you touch 10 lines code, and 2 lines not be covered,  then the report would return 80% coverage for your current pull request. 
