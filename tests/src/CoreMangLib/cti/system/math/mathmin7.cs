using System;
using System.Collections;

/// <summary>
/// System.Math.Min(System.SByte,System.SByte)
/// </summary>
public class MathMin7
{
    public static int Main(string[] args)
    {
        MathMin7 min7 = new MathMin7();
        TestLibrary.TestFramework.BeginTestCase("Testing System.Math.Min(System.SByte,System.SByte)...");

        if (min7.RunTests())
        {
            TestLibrary.TestFramework.EndTestCase();
            TestLibrary.TestFramework.LogInformation("PASS");
            return 100;
        }
        else
        {
            TestLibrary.TestFramework.EndTestCase();
            TestLibrary.TestFramework.LogInformation("FAIL");
            return 0;
        }
    }

    public bool RunTests()
    {
        bool retVal = true;

        TestLibrary.TestFramework.LogInformation("[Positive]");
        retVal = PosTest1() && retVal;

        return retVal;
    }

    public bool PosTest1()
    {
        bool retVal = true;
        TestLibrary.TestFramework.BeginScenario("PosTest1: Verify the return value of Min function...");

        try
        {
            SByte var1 = (SByte)TestLibrary.Generator.GetByte(-55);
            SByte var2 = (SByte)TestLibrary.Generator.GetByte(-55);

            if (var1 > var2)
            {
                if (Math.Min(var1, var2) != var2)
                {
                    TestLibrary.TestFramework.LogError("001", "The return value should be var2!");
                    retVal = false;
                }
            }
            else
            {
                if (Math.Min(var1, var2) != var1)
                {
                    TestLibrary.TestFramework.LogError("002", "The return value should be var1!");
                    retVal = false;
                }
            }
        }
        catch (Exception e)
        {
            TestLibrary.TestFramework.LogError("003", "Unexpected exception occurs: " + e);
            retVal = false;
        }

        return retVal;
    }
}
